const assert=require("node:assert/strict");
const {eligible,desired}=require("../kwin-script/contents/code/main.js");
const g={x:0,y:0,width:1920,height:1080};
const d={}, a="activity";
const base={normalWindow:true,fullScreen:true,output:{name:"DP-1",geometry:g},frameGeometry:g,opacity:1,desktops:[d],activities:[a],resourceClass:"game",desktopFileName:"game"};
const yes=(w)=>eligible(w,d,a,[],[]);
const cases=[
[base,true],[{...base,minimized:true},false],[{...base,hidden:true},false],
[{...base,desktops:[{}]},false],[{...base,activities:["other"]},false],
[{...base,dock:true},false],[{...base,fullScreen:false,noBorder:true,maximizeMode:3},false],
[{...base,fullScreen:false,noBorder:true,maximizeMode:0},true],
[{...base,fullScreen:false,noBorder:true,maximizable:true},false],
[{...base,fullScreen:false,noBorder:true,maximizable:false},true],
[{...base,fullScreen:false,noBorder:true,maximizable:false,frameGeometry:{...g,width:100}},false]
];
for(const [w,expect] of cases) assert.equal(!!yes(w),expect);
assert.equal(eligible(base,d,a,["HDMI-1"],[]),false);
assert.equal(eligible(base,d,a,[],["game"]),false);
assert.equal(desired([base],d,a,[],[]),true);
assert.equal(desired([base,{...base,fullScreen:false,noBorder:false}],d,a,[],[]),false);
assert.equal(desired([base,{...base,fullScreen:false,frameGeometry:{...g,width:100}}],d,a,[],[]),true);
assert.equal(desired([],d,a,[],[]),false);
console.log("17 window assertions passed");
