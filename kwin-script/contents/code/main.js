// KWin 6; no display configuration writes.
function listed(items, value) {
    return !items || !items.length || Array.prototype.indexOf.call(items, value) !== -1;
}
function visible(w, desktop, activity) {
    return w && !w.deleted && !w.minimized && !w.hidden &&
        !w.desktopWindow && !w.dock && !w.specialWindow &&
        listed(w.desktops, desktop) && listed(w.activities, activity);
}
function covers(a, b) {
    return a && b && Math.abs(a.x-b.x)<1 && Math.abs(a.y-b.y)<1 &&
        Math.abs(a.width-b.width)<1 && Math.abs(a.height-b.height)<1;
}
function eligible(w, desktop, activity, allowed, excluded) {
    if (!visible(w, desktop, activity) || !w.output) return false;
    if (allowed.length && allowed.indexOf(w.output.name) === -1) return false;
    if (excluded.indexOf(String(w.resourceClass).toLowerCase()) !== -1 ||
        excluded.indexOf(String(w.desktopFileName).toLowerCase()) !== -1) return false;
    if (w.fullScreen) return true;
    // If maximizeMode is unavailable, conservative fallback avoids most
    // maximized windows: only non-maximizable undecorated full-output windows.
    if (typeof w.maximizeMode === "number" ? w.maximizeMode !== 0 : w.maximizable !== false) return false;
    return w.normalWindow && w.noBorder && !w.decorationHasAlpha &&
        covers(w.frameGeometry, w.output.geometry);
}
function desired(windows, desktop, activity, allowed, excluded) {
    for (var i=0;i<windows.length;i++) {
        var w=windows[i];
        if (!eligible(w,desktop,activity,allowed,excluded)) continue;
        // Best effort: a later opaque normal window covering the same output
        // obscures this candidate. Partial overlap does not count.
        var covered=false;
        for (var j=i+1;j<windows.length;j++) {
            var top=windows[j];
            if (visible(top,desktop,activity) && top.normalWindow &&
                top.opacity === 1 && covers(top.frameGeometry,w.output.geometry)) {
                covered=true; break;
            }
        }
        if (!covered) return true;
    }
    return false;
}
function csv(value) {
    return String(value || "").split(",").map(function(x){return x.trim();}).filter(Boolean);
}
function start() {
    var debounce = new QTimer();
    debounce.interval = 100; debounce.singleShot = true;
    var heartbeat = new QTimer(); heartbeat.interval = 5000;
    var last = null;
    function send(force) {
        var state = desired(workspace.stackingOrder || workspace.windowList(),
            workspace.currentDesktop, workspace.currentActivity,
            csv(readConfig("Outputs", "")), csv(readConfig("ExcludedApps", "")).map(function(x){return x.toLowerCase();}));
        if (!force && last === state) return;
        last = state;
        // Repeated heartbeats deliberately do not rely on successful delivery.
        callDBus("org.fullscreennightlight.Inhibitor", "/Inhibitor",
            "org.fullscreennightlight.Inhibitor", "Refresh", state);
    }
    function schedule() { if (!debounce.active) debounce.start(); }
    function connect(obj, name, fn) { if (obj[name] && obj[name].connect) obj[name].connect(fn); }
    function watch(w) {
        ["fullScreenChanged","frameGeometryChanged","minimizedChanged","outputChanged",
         "desktopsChanged","activitiesChanged","hiddenChanged","stackingOrderChanged",
         "maximizedChanged","decorationChanged","windowClassChanged"].forEach(function(s){connect(w,s,schedule);});
    }
    workspace.windowList().forEach(watch);
    workspace.windowAdded.connect(function(w){watch(w);schedule();});
    ["windowRemoved","windowActivated","currentDesktopChanged","currentActivityChanged","screensChanged"].forEach(function(s){connect(workspace,s,schedule);});
    debounce.timeout.connect(function(){send(false);});
    heartbeat.timeout.connect(function(){send(true);});
    heartbeat.start(); send(true);
    return [debounce, heartbeat];
}
// Keep timer wrappers alive for the lifetime of the KWin script.
var fullscreenNightLightTimers;
if (typeof module !== "undefined") module.exports={eligible:eligible,desired:desired};
else fullscreenNightLightTimers = start();
