
var connection;
var msgs_div = document.getElementById ('msgs')

function message (msg) {
    msgs_div.innerHTML = msg;
}

if (window["WebSocket"]) {
    connection = new WebSocket ("wss://127.0.0.1:9001/term")

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
	}
    }
);

$(document).keypress (
    function () {
	connection.send ('K,' + event.which);
    }
);

