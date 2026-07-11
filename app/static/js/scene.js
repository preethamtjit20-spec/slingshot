/*
 * scene.js — SLINGSHOT cinematic orbital scene (Three.js + GSAP)
 * =============================================================================
 * WHAT THIS FILE IS ABOUT
 * A self-contained, dependency-light 3D "planetary defense" scene rendered behind
 * the mission-control HUD. NO external textures/models are loaded (reliability on
 * stage): Earth, atmosphere, oceans/continents glow, starfield and the asteroid are
 * all procedural shaders/geometry. GSAP drives cinematic camera moves and state
 * transitions so the scene reacts live to what the agents do.
 *
 * PUBLIC API (called by app.js in response to render_command / mock events):
 *   Scene.init(canvas)                 — build + start the render loop
 *   Scene.spawnAsteroid(opts)          — incoming NEO on a trajectory arc toward Earth
 *   Scene.setThreat(level 0..1)        — colour/intensity of the trajectory + Earth mood
 *   Scene.focusThreat()                — cinematic push-in on the asteroid
 *   Scene.focusEarth()                 — pull back to the full planet
 *   Scene.deflect()                    — fire the kinetic impactor; bend the arc to a miss
 *   Scene.impact()                     — (worst case) show the impact flash
 *   Scene.reset()                      — back to calm nominal orbit view
 *
 * USE CASES: idle "nominal watch" beauty shot; anomaly (asteroid detected) drama;
 * deflection success; and a reset between demo runs.
 */
import * as THREE from 'three';
import gsap from 'gsap';

let renderer, scene, camera, clock;
let earth, atmosphere, clouds, starField, asteroid, trail, impactRing;
let threatLevel = 0;
let raf = null;

// --------------------------------------------------------------------- shaders
const EARTH_VERT = `
  varying vec3 vN; varying vec3 vP; varying vec2 vUv;
  void main(){ vUv=uv; vN=normalize(normalMatrix*normal);
    vP=(modelViewMatrix*vec4(position,1.)).xyz;
    gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.); }`;

// Procedural "continents" via layered value-noise; day/night terminator; city-ish glow.
const EARTH_FRAG = `
  precision highp float;
  varying vec3 vN; varying vec3 vP; varying vec2 vUv;
  uniform float uTime; uniform float uThreat;
  float hash(vec2 p){ return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453); }
  float noise(vec2 p){ vec2 i=floor(p),f=fract(p); f=f*f*(3.-2.*f);
    float a=hash(i),b=hash(i+vec2(1,0)),c=hash(i+vec2(0,1)),d=hash(i+vec2(1,1));
    return mix(mix(a,b,f.x),mix(c,d,f.x),f.y); }
  float fbm(vec2 p){ float v=0.,a=.5; for(int i=0;i<5;i++){v+=a*noise(p);p*=2.03;a*=.5;} return v; }
  void main(){
    vec2 uv=vUv*vec2(6.,3.);
    float land=fbm(uv+vec2(uTime*0.005,0.));
    land=smoothstep(.52,.62,land);
    vec3 ocean=mix(vec3(.02,.09,.22),vec3(.03,.20,.42),fbm(uv*2.+uTime*.02));
    vec3 landC=mix(vec3(.05,.22,.10),vec3(.28,.30,.16),fbm(uv*3.));
    vec3 base=mix(ocean,landC,land);
    // lighting: sun from the upper-right
    vec3 L=normalize(vec3(.7,.35,.6));
    float diff=clamp(dot(normalize(vN),L),0.,1.);
    float night=smoothstep(.15,-.05,dot(normalize(vN),L));
    vec3 cityGlow=vec3(1.,.75,.35)*night*land*0.5*(0.6+0.4*noise(uv*22.));
    vec3 col=base*(0.15+1.05*diff)+cityGlow;
    // threat blush over the planet as danger rises
    col=mix(col, col*vec3(1.3,.7,.7)+vec3(.12,0.,0.)*uThreat, uThreat*0.5);
    gl_FragColor=vec4(col,1.);
  }`;

const ATMO_VERT = EARTH_VERT;
const ATMO_FRAG = `
  varying vec3 vN; varying vec3 vP; uniform float uThreat;
  void main(){ vec3 V=normalize(-vP);
    float rim=pow(1.-max(dot(V,normalize(vN)),0.),2.6);
    vec3 calm=vec3(.25,.55,1.); vec3 hot=vec3(1.,.35,.4);
    vec3 c=mix(calm,hot,uThreat);
    gl_FragColor=vec4(c, rim*0.9); }`;

// ------------------------------------------------------------------------ init
function init(canvas){
  renderer = new THREE.WebGLRenderer({canvas, antialias:true, alpha:true});
  renderer.setPixelRatio(Math.min(devicePixelRatio,2));
  renderer.setSize(innerWidth, innerHeight);
  scene = new THREE.Scene();
  clock = new THREE.Clock();

  camera = new THREE.PerspectiveCamera(42, innerWidth/innerHeight, 0.1, 2000);
  camera.position.set(0, 1.4, 9.5);

  scene.add(new THREE.AmbientLight(0x223355, 1.0));
  const key = new THREE.DirectionalLight(0xbfd4ff, 1.6); key.position.set(6,3,5); scene.add(key);

  buildStars();
  buildEarth();
  animate();
  addEventListener('resize', onResize);

  // gentle cinematic intro
  gsap.from(camera.position, {z:16, y:4, duration:2.4, ease:'power3.out'});
  return Scene;
}

function buildStars(){
  const N=2600, g=new THREE.BufferGeometry(), pos=new Float32Array(N*3), col=new Float32Array(N*3);
  for(let i=0;i<N;i++){
    const r=120+Math.random()*400, t=Math.random()*Math.PI*2, p=Math.acos(2*Math.random()-1);
    pos[i*3]=r*Math.sin(p)*Math.cos(t); pos[i*3+1]=r*Math.cos(p); pos[i*3+2]=r*Math.sin(p)*Math.sin(t);
    const s=0.6+Math.random()*0.4; col[i*3]=s; col[i*3+1]=s; col[i*3+2]=Math.min(1,s+0.15);
  }
  g.setAttribute('position',new THREE.BufferAttribute(pos,3));
  g.setAttribute('color',new THREE.BufferAttribute(col,3));
  starField=new THREE.Points(g,new THREE.PointsMaterial({size:0.7,sizeAttenuation:true,vertexColors:true,transparent:true,opacity:.9}));
  scene.add(starField);
}

function buildEarth(){
  const R=3;
  earth=new THREE.Mesh(new THREE.SphereGeometry(R,96,96),
    new THREE.ShaderMaterial({vertexShader:EARTH_VERT,fragmentShader:EARTH_FRAG,
      uniforms:{uTime:{value:0},uThreat:{value:0}}}));
  scene.add(earth);

  atmosphere=new THREE.Mesh(new THREE.SphereGeometry(R*1.14,64,64),
    new THREE.ShaderMaterial({vertexShader:ATMO_VERT,fragmentShader:ATMO_FRAG,
      uniforms:{uThreat:{value:0}}, transparent:true, blending:THREE.AdditiveBlending, side:THREE.BackSide}));
  scene.add(atmosphere);

  // faint orbital ring (defense grid)
  const ring=new THREE.Mesh(new THREE.RingGeometry(R*1.7,R*1.72,128),
    new THREE.MeshBasicMaterial({color:0x2f6fae,transparent:true,opacity:.25,side:THREE.DoubleSide}));
  ring.rotation.x=Math.PI*0.5-0.25; scene.add(ring);
}

// ------------------------------------------------------------------- asteroid
function buildAsteroidMesh(){
  const geo=new THREE.IcosahedronGeometry(0.34,2);
  const p=geo.attributes.position;
  for(let i=0;i<p.count;i++){ // lumpy rock
    const v=new THREE.Vector3().fromBufferAttribute(p,i);
    v.multiplyScalar(1+ (Math.sin(v.x*8)*Math.cos(v.y*7)+Math.random()*0.4)*0.14);
    p.setXYZ(i,v.x,v.y,v.z);
  }
  geo.computeVertexNormals();
  return new THREE.Mesh(geo,new THREE.MeshStandardMaterial({color:0x7c6b5a,roughness:1,metalness:.1,flatShading:true}));
}

// Quadratic-bezier approach curve from deep space toward a near-miss point.
let curve=null, curveT=0, deflected=false;
function makeCurve(miss=false){
  const start=new THREE.Vector3(-16,6,-10);
  const ctrl =new THREE.Vector3(-4,3.5,2);
  const end  = miss ? new THREE.Vector3(6.5,-1.5,3.2) : new THREE.Vector3(0.2,0.1,0.1);
  return new THREE.QuadraticBezierCurve3(start,ctrl,end);
}
function drawTrail(){
  if(trail){ scene.remove(trail); trail.geometry.dispose(); }
  const pts=curve.getPoints(80);
  const g=new THREE.BufferGeometry().setFromPoints(pts);
  trail=new THREE.Line(g,new THREE.LineBasicMaterial({color:0xff5a5a,transparent:true,opacity:.7}));
  scene.add(trail);
}

const Scene = {
  init,
  spawnAsteroid(opts={}){
    if(!asteroid){ asteroid=buildAsteroidMesh(); scene.add(asteroid); }
    deflected=false; curve=makeCurve(false); curveT=0; drawTrail();
    this.setThreat(opts.threat ?? 0.85);
    gsap.fromTo(asteroid.scale,{x:0,y:0,z:0},{x:1,y:1,z:1,duration:.6,ease:'back.out(2)'});
  },
  setThreat(v){
    threatLevel=Math.max(0,Math.min(1,v));
    if(earth) gsap.to(earth.material.uniforms.uThreat,{value:threatLevel,duration:1.2});
    if(atmosphere) gsap.to(atmosphere.material.uniforms.uThreat,{value:threatLevel,duration:1.2});
    if(trail) trail.material.color.setHSL(Math.max(0,(1-threatLevel)*0.33),1,0.6);
  },
  focusThreat(){
    if(!asteroid) return;
    gsap.killTweensOf(camera.position);
    gsap.timeline()
      .to(camera.position,{x:-5.2,y:3.2,z:7.6,duration:1.0,ease:'power2.out'})
      .to(camera.position,{x:-3.0,y:1.4,z:4.6,duration:1.6,ease:'power3.inOut'});
  },
  focusEarth(){ gsap.killTweensOf(camera.position); gsap.to(camera.position,{x:0,y:1.4,z:9.5,duration:2.2,ease:'power3.inOut'}); },
  punchIn(){
    gsap.timeline()
      .to(camera.position,{z:'-=1.8',duration:.45,ease:'power3.in'})
      .to(camera.position,{z:'+=1.8',duration:1.3,ease:'elastic.out(1,0.5)'});
  },
  shake(amp=0.55,dur=0.6){
    if(!camera) return;
    gsap.killTweensOf(camera.position);
    const b={x:camera.position.x,y:camera.position.y,z:camera.position.z};
    const tl=gsap.timeline(), n=10;
    for(let i=0;i<n;i++) tl.to(camera.position,{x:b.x+(Math.random()-.5)*amp,y:b.y+(Math.random()-.5)*amp,z:b.z+(Math.random()-.5)*amp*.5,duration:dur/n,ease:'none'});
    tl.to(camera.position,{x:b.x,y:b.y,z:b.z,duration:.3,ease:'power2.out'});
  },
  warp(){
    // hyperspace jump: FOV punch + rush forward + star-streak, then settle to mission view
    if(!camera) return;
    gsap.killTweensOf(camera.position);
    const tl=gsap.timeline();
    tl.to(camera,{fov:100,duration:.5,ease:'power3.in',onUpdate:()=>camera.updateProjectionMatrix()})
      .to(camera.position,{z:2.2,duration:.5,ease:'power4.in'},0)
      .to(camera,{fov:42,duration:.95,ease:'power2.out',onUpdate:()=>camera.updateProjectionMatrix()})
      .to(camera.position,{z:9.5,x:0,y:1.4,duration:.95,ease:'power2.out'},'-=0.95');
    if(starField) gsap.fromTo(starField.scale,{z:1},{z:9,duration:.5,yoyo:true,repeat:1,ease:'power2.in'});
  },
  deflect(){
    // flash a kinetic impactor streak, then bend the trajectory to a clean miss
    const streak=new THREE.Mesh(new THREE.SphereGeometry(0.08,12,12),
      new THREE.MeshBasicMaterial({color:0x8fefff}));
    scene.add(streak);
    streak.position.set(0.2,0.1,0.1);
    gsap.to(streak.position,{x:asteroid?.position.x,y:asteroid?.position.y,z:asteroid?.position.z,duration:.5,ease:'power2.in',
      onComplete:()=>{ scene.remove(streak);
        // impact ring
        impactRing=new THREE.Mesh(new THREE.RingGeometry(0.1,0.14,32),
          new THREE.MeshBasicMaterial({color:0x9fefff,transparent:true,opacity:.9,side:THREE.DoubleSide}));
        impactRing.position.copy(asteroid.position); scene.add(impactRing);
        gsap.to(impactRing.scale,{x:8,y:8,duration:.8,ease:'power2.out'});
        gsap.to(impactRing.material,{opacity:0,duration:.8,onComplete:()=>scene.remove(impactRing)});
        deflected=true; curve=makeCurve(true); curveT=Math.min(curveT,.5); drawTrail();
        this.setThreat(0.12);
      }});
  },
  impact(){
    const flash=new THREE.PointLight(0xffaa66,0,50); flash.position.set(0,0,0); scene.add(flash);
    gsap.to(flash,{intensity:40,duration:.15,yoyo:true,repeat:1,onComplete:()=>scene.remove(flash)});
    this.setThreat(1);
  },
  reset(){
    if(asteroid){ scene.remove(asteroid); asteroid=null; }
    if(trail){ scene.remove(trail); trail=null; }
    this.setThreat(0); this.focusEarth();
  },
};

function animate(){
  raf=requestAnimationFrame(animate);
  const dt=clock.getDelta(), t=clock.elapsedTime;
  if(earth){ earth.rotation.y+=dt*0.03; earth.material.uniforms.uTime.value=t; }
  if(clouds) clouds.rotation.y+=dt*0.04;
  if(starField) starField.rotation.y+=dt*0.003;
  if(asteroid && curve){
    if(!deflected || curveT<1) curveT=Math.min(1,curveT+dt*0.03);
    const p=curve.getPoint(curveT); asteroid.position.copy(p);
    asteroid.rotation.x+=dt*0.6; asteroid.rotation.y+=dt*0.9;
  }
  renderer.render(scene,camera);
}
function onResize(){ camera.aspect=innerWidth/innerHeight; camera.updateProjectionMatrix(); renderer.setSize(innerWidth,innerHeight); }

export default Scene;
