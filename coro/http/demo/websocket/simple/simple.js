
var connection;
var msgs_div = document.getElementById ('msgs')

function message (msg) {
    msgs_div.innerHTML = msg;
}

if (window["WebSocket"]) {

    // build the websocket uri from this document's location.
    var loc = window.location, ws_uri;
    if (loc.protocol === "https:") {
	ws_uri = "wss:";
    } else {
	ws_uri = "ws:";
    }
    ws_uri += "//" + loc.host;

    connection = new WebSocket(ws_uri + "/sketch");

    connection.onopen = function () {
	message ('connected')
    };

    connection.onclose = function (event) {
	message ('disconnected')
    }
    
    connection.onmessage = function (event) {
	message ('websocket event: ' + event.data)
	var data = event.data.split (',')
	switch (data[0]) {
	case 'D':
	    draw (parseInt(data[1]), parseInt(data[2]), parseInt(data[3]), parseInt(data[4]))
	    break;
	case 'E':
	    undraw (parseInt(data[1]), parseInt(data[2]), parseInt(data[3]), parseInt(data[4]))
	    break;
	case 'CD':
	    context.fillStyle = 'rgb(255, 255, 255)'
	    context.fillRect (0, 0, 1024, 1024)
	    break;
	}
    }
}

var canvas = document.getElementById ('canvas')
canvas.style.cursor = 'crosshair'
var context = canvas.getContext ('2d')

function draw (x0, y0, x1, y1) {
    context.strokeStyle = 'rgba(0,0,0,255)'
    context.beginPath()
    context.moveTo (x0, y0)
    context.lineTo (x1, y1)
    context.closePath()
    context.stroke()
}

function undraw (x0, y0, x1, y1) {
    context.strokeStyle = 'rgba(255,255,255,255)'
    context.beginPath()
    context.moveTo (x0, y0)
    context.lineTo (x1, y1)
    context.closePath()
    context.stroke()
}

document.addEventListener ('mousedown', on_mouse_down, false)
document.addEventListener ('mouseup', on_mouse_up, false)
document.addEventListener ('mousemove', on_mouse_move, false)
document.addEventListener ('keydown', on_key_down, false)
document.addEventListener ('keyup', on_key_up, false)

function clear_drawing() {
    connection.send ('CD')
}
function on_mouse_down (event) {
    connection.send ('MD,' + event.clientX + ',' + event.clientY)
}
function on_mouse_up (event) {
    connection.send ('MU,' + event.clientX + ',' + event.clientY)
}
function on_mouse_move (event) {
    connection.send ('MM,' + event.clientX + ',' + event.clientY)
}
function on_key_down (event) {
    connection.send ('KD,' + event.keyCode)
}
function on_key_up (event) {
    connection.send ('KU,' + event.keyCode)
}
