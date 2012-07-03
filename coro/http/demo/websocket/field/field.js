
var connection;
var msgs_div = document.getElementById ('msgs')

function message (msg) {
    msgs_div.innerHTML = msg;
}

if (window["WebSocket"]) {
    connection = new WebSocket("ws://127.0.0.1:9001/field")

    connection.onopen = function () {
	message ('connected')
    };

    connection.onclose = function (event) {
	message ('disconnected')
    }
    
    connection.onmessage = function (event) {
	//message ('websocket event: ' + event.data)
	switch (event.data[0]) {
	case 'F':
	    // draw field
	    var elems = event.data.split ('|')
	    context.clearRect (0, 0, 1024, 1024);
	    context.fillStyle = 'rgb(0,0,0,128)';
	    for (i=0; i < elems.length; i++) {
		var elem = elems[i];
		var p = elem.split (',')
		switch (p[0]) {
		case 'B':
		    context.fillStyle = p[1];
		    context.fillRect (parseInt (p[2]), parseInt (p[3]), parseInt (p[4]), parseInt (p[5]));
		    break;
		}
	    }
	    break;
	case 'C':
	    context.clearRect (0, 0, 1024, 1024);
	    break;
	case 'M':
	    message (event.data);
	    break;
	}
    }
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
