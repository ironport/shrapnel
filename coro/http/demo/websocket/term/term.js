
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

    // open connection
    var connection = new WebSocket(ws_uri + '/term');

    connection.onopen = function () {
	message ('connected')
    };

    connection.onclose = function (event) {
	message ('disconnected')
    }
    
    connection.onmessage = function (event) {
	message ('event: ' + event.data[0])
	var data = event.data;
	switch (data[0]) {
	case 'D':
	    $('#term').append (data.substring (1, data.length));
	    document.getElementById ('cursor').scrollIntoView();
	    break;
	case 'I':
	    $('#input').append (data.substring (1, data.length));
	    break;
	case 'B':
	    $('#input').html (data.substring (1, data.length));
	    break;
	case 'C':
	    $('#input').empty();
	    break;
	}
    }
}

var term = document.getElementById ('term');

$(document).keydown (
    function() {
	if (event.which == 8) {
	    // backspace
	    connection.send ('B');
	    return false;
	}
    }
);

$(document).keypress (
    function () {
	connection.send ('K,' + event.which);
    }
);

