# Copyright (c) 2002-2011 IronPort Systems and Cisco Systems
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# $Header: /cvsroot/ap/shrapnel/coro/print_profile.py,v 1.1 2006/11/30 21:58:41 ehuss Exp $

"""Display profile data as HTML.

TODO
====
- The javascript sorting code has a weird behavior.  If you click on a column
  to sort it, then click on a different column, the click on the previous
  column, the sort order changes.  I would prefer it it just went with the
  previous sort order.  However, fixing it is not obvious to me.

"""

import urllib
import cgi
import sys
import coro.profiler
import cPickle
import time

PER_COLUMNS = ('ticks', 'utime', 'stime')

# from http://kryogenix.org/code/browser/sorttable/
# Note: I changed the default sort direction to 'down'
sortable_js = """addEvent(window, "load", sortables_init);

var SORT_COLUMN_INDEX;

function sortables_init() {
    // Find all tables with class sortable and make them sortable
    if (!document.getElementsByTagName) return;
    tbls = document.getElementsByTagName("table");
    for (ti=0;ti<tbls.length;ti++) {
        thisTbl = tbls[ti];
        if (((' '+thisTbl.className+' ').indexOf("sortable") != -1) && (thisTbl.id)) {
            //initTable(thisTbl.id);
            ts_makeSortable(thisTbl);
        }
    }
}

function ts_makeSortable(table) {
    if (table.rows && table.rows.length > 0) {
        var firstRow = table.rows[0];
    }
    if (!firstRow) return;

    // We have a first row: assume it's the header, and make its contents clickable links
    for (var i=0;i<firstRow.cells.length;i++) {
        var cell = firstRow.cells[i];
        var txt = ts_getInnerText(cell);
        cell.innerHTML = '<a href="#" class="sortheader" '+
        'onclick="ts_resortTable(this, '+i+');return false;">' +
        txt+'<span class="sortarrow">&nbsp;&nbsp;&nbsp;</span></a>';
    }
}

function ts_getInnerText(el) {
    if (typeof el == "string") return el;
    if (typeof el == "undefined") { return el };
    if (el.innerText) return el.innerText;  //Not needed but it is faster
    var str = "";

    var cs = el.childNodes;
    var l = cs.length;
    for (var i = 0; i < l; i++) {
        switch (cs[i].nodeType) {
            case 1: //ELEMENT_NODE
                str += ts_getInnerText(cs[i]);
                break;
            case 3: //TEXT_NODE
                str += cs[i].nodeValue;
                break;
        }
    }
    return str;
}

function ts_resortTable(lnk,clid) {
    // get the span
    var span;
    for (var ci=0;ci<lnk.childNodes.length;ci++) {
        if (lnk.childNodes[ci].tagName && lnk.childNodes[ci].tagName.toLowerCase() == 'span') span = lnk.childNodes[ci];
    }
    var spantext = ts_getInnerText(span);
    var td = lnk.parentNode;
    var column = clid || td.cellIndex;
    var table = getParent(td,'TABLE');

    // Work out a type for the column
    if (table.rows.length <= 1) return;
    var itm = ts_getInnerText(table.rows[1].cells[column]);
    //sortfn = ts_sort_caseinsensitive;
    //if (itm.match(/^\d\d[\/-]\d\d[\/-]\d\d\d\d$/)) sortfn = ts_sort_date;
    //if (itm.match(/^\d\d[\/-]\d\d[\/-]\d\d$/)) sortfn = ts_sort_date;
    //if (itm.match(/^[\ufffd$]/)) sortfn = ts_sort_currency;
    //if (itm.match(/^[\d\.]+$/)) sortfn = ts_sort_numeric;
    sortfn = ts_sort_numeric;
    SORT_COLUMN_INDEX = column;
    var firstRow = new Array();
    var newRows = new Array();
    for (i=0;i<table.rows[0].length;i++) { firstRow[i] = table.rows[0][i]; }
    for (j=1;j<table.rows.length;j++) { newRows[j-1] = table.rows[j]; }

    newRows.sort(sortfn);

    if (span.getAttribute("sortdir") == 'up') {
        ARROW = '&nbsp;&nbsp;&darr;';
        span.setAttribute('sortdir','down');
    } else {
        ARROW = '&nbsp;&nbsp;&uarr;';
        newRows.reverse();
        span.setAttribute('sortdir','up');
    }

    // We appendChild rows that already exist to the tbody, so it moves them rather than creating new ones
    // don't do sortbottom rows
    for (i=0;i<newRows.length;i++) {
        if (!newRows[i].className || (newRows[i].className && (newRows[i].className.indexOf('sortbottom') == -1)))
             table.tBodies[0].appendChild(newRows[i]);
    }
    // do sortbottom rows only
    for (i=0;i<newRows.length;i++) {
        if (newRows[i].className && (newRows[i].className.indexOf('sortbottom') != -1))
            table.tBodies[0].appendChild(newRows[i]);
    }

    // Delete any other arrows there may be showing
    var allspans = document.getElementsByTagName("span");
    for (var ci=0;ci<allspans.length;ci++) {
        if (allspans[ci].className == 'sortarrow') {
            if (getParent(allspans[ci],"table") == getParent(lnk,"table")) { // in the same table as us?
                allspans[ci].innerHTML = '&nbsp;&nbsp;&nbsp;';
            }
        }
    }

    span.innerHTML = ARROW;
}

function getParent(el, pTagName) {
    if (el == null) return null;
    else if (el.nodeType == 1 && el.tagName.toLowerCase() == pTagName.toLowerCase())
        // Gecko bug, supposed to be uppercase
        return el;
    else
        return getParent(el.parentNode, pTagName);
}
function ts_sort_date(a,b) {
    // y2k notes: two digit years less than 50 are treated as 20XX, greater than 50 are treated as 19XX
    aa = ts_getInnerText(a.cells[SORT_COLUMN_INDEX]);
    bb = ts_getInnerText(b.cells[SORT_COLUMN_INDEX]);
    if (aa.length == 10) {
        dt1 = aa.substr(6,4)+aa.substr(3,2)+aa.substr(0,2);
    } else {
        yr = aa.substr(6,2);
        if (parseInt(yr) < 50) { yr = '20'+yr; } else { yr = '19'+yr; }
        dt1 = yr+aa.substr(3,2)+aa.substr(0,2);
    }
    if (bb.length == 10) {
        dt2 = bb.substr(6,4)+bb.substr(3,2)+bb.substr(0,2);
    } else {
        yr = bb.substr(6,2);
        if (parseInt(yr) < 50) { yr = '20'+yr; } else { yr = '19'+yr; }
        dt2 = yr+bb.substr(3,2)+bb.substr(0,2);
    }
    if (dt1==dt2) return 0;
    if (dt1<dt2) return -1;
    return 1;
}

function ts_sort_currency(a,b) {
    aa = ts_getInnerText(a.cells[SORT_COLUMN_INDEX]).replace(/[^0-9.]/g,'');
    bb = ts_getInnerText(b.cells[SORT_COLUMN_INDEX]).replace(/[^0-9.]/g,'');
    return parseFloat(aa) - parseFloat(bb);
}

function ts_sort_numeric(a,b) {
    aa = parseFloat(ts_getInnerText(a.cells[SORT_COLUMN_INDEX]));
    if (isNaN(aa)) aa = 0;
    bb = parseFloat(ts_getInnerText(b.cells[SORT_COLUMN_INDEX]));
    if (isNaN(bb)) bb = 0;
    return aa-bb;
}

function ts_sort_caseinsensitive(a,b) {
    aa = ts_getInnerText(a.cells[SORT_COLUMN_INDEX]).toLowerCase();
    bb = ts_getInnerText(b.cells[SORT_COLUMN_INDEX]).toLowerCase();
    if (aa==bb) return 0;
    if (aa<bb) return -1;
    return 1;
}

function ts_sort_default(a,b) {
    aa = ts_getInnerText(a.cells[SORT_COLUMN_INDEX]);
    bb = ts_getInnerText(b.cells[SORT_COLUMN_INDEX]);
    if (aa==bb) return 0;
    if (aa<bb) return -1;
    return 1;
}


function addEvent(elm, evType, fn, useCapture)
// addEvent and removeEvent
// cross-browser event handling for IE5+,  NS6 and Mozilla
// By Scott Andrew
{
  if (elm.addEventListener){
    elm.addEventListener(evType, fn, useCapture);
    return true;
  } else if (elm.attachEvent){
    var r = elm.attachEvent("on"+evType, fn);
    return r;
  } else {
    alert("Handler could not be removed");
  }
}
"""

def _mapfuns(d1, d2):
    """
    Given two dicts, d1 (k1 -> v1) and d2 (k2 -> v2), returns a dict which has
    the mapping (k1 -> k2) such that _name(k1) == _name(k2).
    """
    def _name(fn):
        """
        Strips the line number at the end if any.
        Eg. 'foo.py:23' -> 'foo.py', 'foo:bar.py' -> 'foo:bar.py' etc.
        """
        parts = fn.rsplit(':', 1)
        try:
            int(parts[1])
            return parts[0]
        except Exception:
            return fn

    m1 = [(_name(f), f) for f in d1]
    m2 = dict([(_name(f), f) for f in d2])
    return dict([(v, m2[k]) for k, v in m1 if k in m2])


class profile_data:

    """

    profile_data = {function_string: data_tuple}

    data_tuple[0] is always calls

    call_data = {caller_string: [(callee_string, call_count),...])
                }

    """

    def __init__(self, filename):
        self._load(filename)

    def _load(self, filename):
        f = open(filename)
        header = f.read(len(coro.profiler.MAGIC))
        if header != coro.profiler.MAGIC:
            err('Header not valid.')
        self.bench_type, self.headings, self.time = cPickle.load(f)
        self.profile_data = cPickle.load(f)
        self.call_data = cPickle.load(f)

    def process(self, other_profile):
        self._print_header()
        self._print_timings(False, other_profile)
        print '<hr>'
        self._print_timings(True, other_profile)
        self._print_call_graph()
        self._print_footer()

    def _print_timings(self, aggregate, other_profile):
        if aggregate:
            print '<h2>Aggregate Timings</h2>'
        else:
            print '<h2>Non-Aggregate Timings</h2>'

        # Find any columns that have all zeros and skip them.
        has_nonzero = {}
        # Also determine the sum for the column.
        column_sums = [0] * len(self.headings)
        empty_cols = [0] * len(self.headings)

        for heading in self.headings:
            has_nonzero[heading] = False
        for function_string, (calls, data_tuple, aggregate_data_tuple) in self.profile_data.iteritems():
            if function_string != '<wait>':
                for i, heading in enumerate(self.headings):
                    if aggregate:
                        data_item = aggregate_data_tuple[i]
                    else:
                        data_item = data_tuple[i]
                    if data_item:
                        has_nonzero[heading] = True
                        column_sums[i] += data_item
        skip_headings = []
        for heading, nonzero in has_nonzero.items():
            if not nonzero:
                skip_headings.append(heading)

        print '<table id="t1" class="sortable" border=1 cellpadding=2 cellspacing=0>'
        print '  <tr>'
        print '    <th>calls</th>'
        for heading in self.headings:
            if heading not in skip_headings:
                print '    <th>%s</th>' % (heading,)
                if heading in PER_COLUMNS:
                    print '    <th>%s/call</th>' % (heading,)
        print '    <th>Function</th>'
        print '  </tr>'

        m = _mapfuns(self.profile_data, other_profile)
        for function_string, (calls, data_tuple, aggregate_data_tuple) in self.profile_data.iteritems():
            try:
                calls2, data_tuple2, aggregate_data_tuple2 = other_profile[m[function_string]]
            except KeyError:
                calls2, data_tuple2, aggregate_data_tuple2 = 0, empty_cols, empty_cols
            print '  <tr align=right>'
            print '    <td>%s</td>' % (calls - calls2, )
            for i, heading in enumerate(self.headings):
                if heading not in skip_headings:
                    if aggregate:
                        data_item = aggregate_data_tuple[i] - aggregate_data_tuple2[i]
                    else:
                        data_item = data_tuple[i] - data_tuple2[i]
                    if isinstance(data_item, float):
                        value = '%.6f' % (data_item,)
                    else:
                        value = data_item
                    if data_item and function_string != '<wait>':
                        pct = ' (%.2f%%)' % ((float(data_item) / column_sums[i]) * 100,)
                    else:
                        pct = ''
                    print '    <td>%s%s</td>' % (value, pct)
                    if heading in PER_COLUMNS:
                        if calls == 0:
                            per = data_item
                        else:
                            if isinstance(data_item, float):
                                per = '%.6f' % (data_item / calls,)
                            else:
                                per = data_item / calls
                        print '    <td>%s</td>' % (per, )
            print '    <td align=left><a name="tt_%s"></a><a href="#cg_%s">%s</a></td>' % (
                urllib.quote_plus(function_string),
                urllib.quote_plus(function_string),
                cgi.escape(function_string, quote=True)
            )
            print '  </tr>'
        print '</table>'
        print '<p><tt>/call</tt> columns represent the time spent in that function per call <b>on average</b>.'
        print '<p>Columns with all zeros are not displayed.'

    def _print_call_graph(self):
        # self.call_data is caller->callee, make a reverse graph of callee->caller
        rg = {}
        for caller_string, callees in self.call_data.iteritems():
            for callee_string, call_count in callees:
                if callee_string in rg:
                    rg[callee_string].append((caller_string, call_count))
                else:
                    rg[callee_string] = [(caller_string, call_count)]

        functions = self.profile_data.items()
        functions.sort()

        for function_string, (calls, data_tuple, aggregate_data_tuple) in functions:
            print '<hr>'
            print '<tt><a name="cg_%s">%s</a> -- ' % (
                urllib.quote_plus(function_string),
                cgi.escape(function_string, quote=True)
            )
            for (data_item, heading) in zip(data_tuple, self.headings):
                if data_item != 0:
                    print '%s=%s' % (heading, data_item)
            print '</tt>'
            print '<pre>'
            # Print callers.
            if function_string in rg:
                l = []
                for caller, count in rg[function_string]:
                    l.append((caller, count))
                l.sort(lambda a, b: cmp(a[1], b[1]))
                for caller, count in l:
                    print '%10i/%-10i (%04.1f%%) <a href="#tt_%s">%s</a>' % (
                        count,
                        calls,
                        (float(count) / calls) * 100,
                        urllib.quote_plus(caller),
                        cgi.escape(caller, quote=True)
                    )

            print '%15i           <b>%s</b>' % (calls, function_string)

            # Print callees.
            callees2 = []
            callees = self.call_data.get(function_string, ())
            for callee_string, call_count in callees:
                callee_calls = self.profile_data.get(callee_string, [1])[0]
                callees2.append((callee_string, call_count, callee_calls))
            callees2.sort(lambda a, b: cmp(a[1], b[1]))
            for callee_string, call_count, callee_calls in callees2:
                print '%10i/%-10i (%04.1f%%) <a href="#tt_%s">%s</a>' % (
                    call_count,
                    callee_calls,
                    (float(call_count) / callee_calls) * 100,
                    urllib.quote_plus(callee_string),
                    cgi.escape(callee_string, quote=True)
                )
            print '</pre>'

        print '<hr>'
        print 'Description of output:'
        print '<pre>'
        print 'filename:funcname:lineno -- prof_data'
        print
        print '   caller_x/caller_y   (%) caller'
        print '    total_calls           <b>function</b>'
        print '   callee_x/callee_y   (%) callee'
        print
        print 'caller_x is the number of times caller made a call to this function.'
        print 'caller_y is the total number of calls to the function from all callers combined.'
        print
        print 'callee_x is the total number of times the function called this callee.'
        print 'callee_y is the total number of calls to this callee from all functions in the program.'
        print
        print 'Profile data values of 0 are not displayed.'

    def _print_header(self):
        print '<html><head><title>Shrapnel Profile</title></head><body bgcolor="#ffffff">'
        print '<script type="text/javascript"><!--'
        print sortable_js
        print '// -->'
        print '</script>'
        print '<h1>Shrapnel Profile Results</h1>'
        print '<hr>'

    def _print_footer(self):
        print '<hr>'
        print 'Profile data collected at %s<br>' % (time.ctime(self.time),)
        print 'Output generated at %s<br>' % (time.ctime(),)
        print '</body></html>'

def err(msg):
    sys.stderr.write(msg + '\n')
    sys.exit(1)

def usage():
    print 'Usage: print_profile.py profile_filename [other_profile]'
    print
    print ' print_profile.py filename             -> Convert Profile data to HTML'
    print ' print_profile.py filename1, filename2 -> Compare timings between profile results in file1 and file2'
    print
    print 'Output HTML is sent to stdout'

def main(baseline, otherfile=None):
    data = profile_data(baseline)
    other_profile = {}
    if otherfile:
        data2 = profile_data(otherfile)
        if data.bench_type != data2.bench_type:
            print 'Cannot Compare. Bench types are different.'
            return
        other_profile = data2.profile_data
    data.process(other_profile)

if __name__ == '__main__':
    if len(sys.argv) not in (2, 3):
        usage()
        sys.exit(1)

    baseline = sys.argv[1]
    otherfile = sys.argv[2] if len(sys.argv) == 3 else None
    main(baseline, otherfile)
