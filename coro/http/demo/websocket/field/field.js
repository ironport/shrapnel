var connection;
var msgs_div = document.getElementById ('msgs')
var draw_cmds = [];

function message (msg) {
    msgs_div.innerHTML = msg;
}

if (window["WebSocket"]) {

    var loc = window.location, new_uri;
    if (loc.protocol === "https:") {
	ws_uri = "wss:";
    } else {
	ws_uri = "ws:";
    }
    ws_uri += "//" + loc.host;

    connection = new WebSocket(ws_uri + "/field");

    connection.onopen = function () {
	message ('connected')
	animate();
    };

    connection.onclose = function (event) {
	message ('disconnected')
    }
    
    connection.onmessage = function (event) {
	//message ('websocket event: ' + event.data)
	switch (event.data[0]) {
	case 'F':
	    draw_cmds = event.data.split ('|');
	    break;
	case 'M':
	    message (event.data);
	    break;
	}
    }
}

window.requestAnimFrame = (function(callback){
    return window.requestAnimationFrame ||
    window.webkitRequestAnimationFrame ||
    window.mozRequestAnimationFrame ||
    window.oRequestAnimationFrame ||
    window.msRequestAnimationFrame ||
    function(callback){
        window.setTimeout(callback, 1000 / 60);
    };
})();

function animate() {
    context.clearRect (0, 0, 1024, 1024);
    context.strokeStyle = 'rgb(0,0,0,0)';
    for (i=0; i < draw_cmds.length; i++) {
	var cmd = draw_cmds[i];
	var p = cmd.split (',')
	switch (p[0]) {
	case 'B':
	    context.fillStyle = p[1];
	    context.fillRect (parseInt (p[2]), parseInt (p[3]), parseInt (p[4]), parseInt (p[5]));
	    context.strokeRect (parseInt (p[2]), parseInt (p[3]), parseInt (p[4]), parseInt (p[5]));
	    break;
	case 'C':
	    context.fillStyle = p[1];
	    draw_circle (parseInt (p[2]), parseInt (p[3]), parseInt (p[4]));
	    break;
	}
    }
    requestAnimFrame (animate);
}


function draw_circle (x0, y0, r) {
    // context.fillRect (x0-r, y0-r, r*2, r*2);
    context.beginPath();
    context.arc (x0, y0, r, 0, 2*Math.PI);
    context.closePath();
    context.fill();
    context.stroke();
}

var canvas = document.getElementById ('canvas')
var context = canvas.getContext ('2d')

document.addEventListener ('mousedown', on_mouse_down, false)
document.addEventListener ('mouseup', on_mouse_up, false)
document.addEventListener ('mousemove', on_mouse_move, false)
document.addEventListener ('keydown', on_key_down, false)
document.addEventListener ('keyup', on_key_up, false)

document.addEventListener ('touchstart', on_touch_start, false)
document.addEventListener ('touchmove', on_touch_move, false)
document.addEventListener ('touchend', on_touch_end, false)

function on_mouse_down (event) {
    connection.send ('MD,' + event.clientX + ',' + event.clientY)
}
function on_mouse_up (event) {
    connection.send ('MU,' + event.clientX + ',' + event.clientY)
}
function on_mouse_move (event) {
    connection.send ('MM,' + event.clientX + ',' + event.clientY)
}
function make_touch_list (tl) {
    var result = new Array (tl.length);
    for (i=0; i < tl.length; i++) {
	result[i] = tl[i].pageX + '.' + tl[i].pageY;
    }
    return result.join (',');
}
function on_touch_start (event) {
    event.preventDefault();
    connection.send ('TS,' + make_touch_list (event.touches));
}
function on_touch_end (event) {
    // no touch list on this one...
    connection.send ('TE');
}
function on_touch_move (event) {
    connection.send ('TM,' + make_touch_list (event.touches));
}
function on_key_down (event) {
    connection.send ('KD,' + event.keyCode)
}
function on_key_up (event) {
    connection.send ('KU,' + event.keyCode)
}
