//#region \0rolldown/runtime.js
var __defProp = Object.defineProperty;
var __exportAll = (all, no_symbols) => {
	let target = {};
	for (var name in all) __defProp(target, name, {
		get: all[name],
		enumerable: true
	});
	if (!no_symbols) __defProp(target, Symbol.toStringTag, { value: "Module" });
	return target;
};
//#endregion
//#region \0vite/modulepreload-polyfill.js
(function polyfill() {
	const relList = document.createElement("link").relList;
	if (relList && relList.supports && relList.supports("modulepreload")) return;
	for (const link of document.querySelectorAll("link[rel=\"modulepreload\"]")) processPreload(link);
	new MutationObserver((mutations) => {
		for (const mutation of mutations) {
			if (mutation.type !== "childList") continue;
			for (const node of mutation.addedNodes) if (node.tagName === "LINK" && node.rel === "modulepreload") processPreload(node);
		}
	}).observe(document, {
		childList: true,
		subtree: true
	});
	function getFetchOpts(link) {
		const fetchOpts = {};
		if (link.integrity) fetchOpts.integrity = link.integrity;
		if (link.referrerPolicy) fetchOpts.referrerPolicy = link.referrerPolicy;
		if (link.crossOrigin === "use-credentials") fetchOpts.credentials = "include";
		else if (link.crossOrigin === "anonymous") fetchOpts.credentials = "omit";
		else fetchOpts.credentials = "same-origin";
		return fetchOpts;
	}
	function processPreload(link) {
		if (link.ep) return;
		link.ep = true;
		const fetchOpts = getFetchOpts(link);
		fetch(link.href, fetchOpts);
	}
})();
//#endregion
//#region node_modules/preact/dist/preact.module.js
var n$1;
var l$1;
var u$1;
var i$1;
var r$1;
var o$1;
var e$1;
var f$1;
var c$1;
var a$1;
var s$1;
var h$1;
var p$1;
var v$1;
var d$1 = {};
var w$1 = [];
var _$1 = /acit|ex(?:s|g|n|p|$)|rph|grid|ows|mnc|ntw|ine[ch]|zoo|^ord|itera/i;
var g = Array.isArray;
function m$2(n, l) {
	for (var u in l) n[u] = l[u];
	return n;
}
function b(n) {
	n && n.parentNode && n.parentNode.removeChild(n);
}
function k$1(l, u, t) {
	var i, r, o, e = {};
	for (o in u) "key" == o ? i = u[o] : "ref" == o ? r = u[o] : e[o] = u[o];
	if (arguments.length > 2 && (e.children = arguments.length > 3 ? n$1.call(arguments, 2) : t), "function" == typeof l && null != l.defaultProps) for (o in l.defaultProps) void 0 === e[o] && (e[o] = l.defaultProps[o]);
	return x(l, e, i, r, null);
}
function x(n, t, i, r, o) {
	var e = {
		type: n,
		props: t,
		key: i,
		ref: r,
		__k: null,
		__: null,
		__b: 0,
		__e: null,
		__c: null,
		constructor: void 0,
		__v: null == o ? ++u$1 : o,
		__i: -1,
		__u: 0
	};
	return null == o && null != l$1.vnode && l$1.vnode(e), e;
}
function S(n) {
	return n.children;
}
function C$1(n, l) {
	this.props = n, this.context = l;
}
function $(n, l) {
	if (null == l) return n.__ ? $(n.__, n.__i + 1) : null;
	for (var u; l < n.__k.length; l++) if (null != (u = n.__k[l]) && null != u.__e) return u.__e;
	return "function" == typeof n.type ? $(n) : null;
}
function I(n) {
	if (n.__P && n.__d) {
		var u = n.__v, t = u.__e, i = [], r = [], o = m$2({}, u);
		o.__v = u.__v + 1, l$1.vnode && l$1.vnode(o), q(n.__P, o, u, n.__n, n.__P.namespaceURI, 32 & u.__u ? [t] : null, i, null == t ? $(u) : t, !!(32 & u.__u), r), o.__v = u.__v, o.__.__k[o.__i] = o, D$1(i, o, r), u.__e = u.__ = null, o.__e != t && P(o);
	}
}
function P(n) {
	if (null != (n = n.__) && null != n.__c) return n.__e = n.__c.base = null, n.__k.some(function(l) {
		if (null != l && null != l.__e) return n.__e = n.__c.base = l.__e;
	}), P(n);
}
function A$1(n) {
	(!n.__d && (n.__d = !0) && i$1.push(n) && !H.__r++ || r$1 != l$1.debounceRendering) && ((r$1 = l$1.debounceRendering) || o$1)(H);
}
function H() {
	try {
		for (var n, l = 1; i$1.length;) i$1.length > l && i$1.sort(e$1), n = i$1.shift(), l = i$1.length, I(n);
	} finally {
		i$1.length = H.__r = 0;
	}
}
function L(n, l, u, t, i, r, o, e, f, c, a) {
	var s, h, p, v, y, _, g, m = t && t.__k || w$1, b = l.length;
	for (f = T$1(u, l, m, f, b), s = 0; s < b; s++) null != (p = u.__k[s]) && (h = -1 != p.__i && m[p.__i] || d$1, p.__i = s, _ = q(n, p, h, i, r, o, e, f, c, a), v = p.__e, p.ref && h.ref != p.ref && (h.ref && J(h.ref, null, p), a.push(p.ref, p.__c || v, p)), null == y && null != v && (y = v), (g = !!(4 & p.__u)) || h.__k === p.__k ? (f = j$1(p, f, n, g), g && h.__e && (h.__e = null)) : "function" == typeof p.type && void 0 !== _ ? f = _ : v && (f = v.nextSibling), p.__u &= -7);
	return u.__e = y, f;
}
function T$1(n, l, u, t, i) {
	var r, o, e, f, c, a = u.length, s = a, h = 0;
	for (n.__k = new Array(i), r = 0; r < i; r++) null != (o = l[r]) && "boolean" != typeof o && "function" != typeof o ? ("string" == typeof o || "number" == typeof o || "bigint" == typeof o || o.constructor == String ? o = n.__k[r] = x(null, o, null, null, null) : g(o) ? o = n.__k[r] = x(S, { children: o }, null, null, null) : void 0 === o.constructor && o.__b > 0 ? o = n.__k[r] = x(o.type, o.props, o.key, o.ref ? o.ref : null, o.__v) : n.__k[r] = o, f = r + h, o.__ = n, o.__b = n.__b + 1, e = null, -1 != (c = o.__i = O(o, u, f, s)) && (s--, (e = u[c]) && (e.__u |= 2)), null == e || null == e.__v ? (-1 == c && (i > a ? h-- : i < a && h++), "function" != typeof o.type && (o.__u |= 4)) : c != f && (c == f - 1 ? h-- : c == f + 1 ? h++ : (c > f ? h-- : h++, o.__u |= 4))) : n.__k[r] = null;
	if (s) for (r = 0; r < a; r++) null != (e = u[r]) && 0 == (2 & e.__u) && (e.__e == t && (t = $(e)), K(e, e));
	return t;
}
function j$1(n, l, u, t) {
	var i, r;
	if ("function" == typeof n.type) {
		for (i = n.__k, r = 0; i && r < i.length; r++) i[r] && (i[r].__ = n, l = j$1(i[r], l, u, t));
		return l;
	}
	n.__e != l && (t && (l && n.type && !l.parentNode && (l = $(n)), u.insertBefore(n.__e, l || null)), l = n.__e);
	do
		l = l && l.nextSibling;
	while (null != l && 8 == l.nodeType);
	return l;
}
function O(n, l, u, t) {
	var i, r, o, e = n.key, f = n.type, c = l[u], a = null != c && 0 == (2 & c.__u);
	if (null === c && null == e || a && e == c.key && f == c.type) return u;
	if (t > (a ? 1 : 0)) {
		for (i = u - 1, r = u + 1; i >= 0 || r < l.length;) if (null != (c = l[o = i >= 0 ? i-- : r++]) && 0 == (2 & c.__u) && e == c.key && f == c.type) return o;
	}
	return -1;
}
function z$1(n, l, u) {
	"-" == l[0] ? n.setProperty(l, null == u ? "" : u) : n[l] = null == u ? "" : "number" != typeof u || _$1.test(l) ? u : u + "px";
}
function N(n, l, u, t, i) {
	var r, o;
	n: if ("style" == l) if ("string" == typeof u) n.style.cssText = u;
	else {
		if ("string" == typeof t && (n.style.cssText = t = ""), t) for (l in t) u && l in u || z$1(n.style, l, "");
		if (u) for (l in u) t && u[l] == t[l] || z$1(n.style, l, u[l]);
	}
	else if ("o" == l[0] && "n" == l[1]) r = l != (l = l.replace(s$1, "$1")), o = l.toLowerCase(), l = o in n || "onFocusOut" == l || "onFocusIn" == l ? o.slice(2) : l.slice(2), n.l || (n.l = {}), n.l[l + r] = u, u ? t ? u[a$1] = t[a$1] : (u[a$1] = h$1, n.addEventListener(l, r ? v$1 : p$1, r)) : n.removeEventListener(l, r ? v$1 : p$1, r);
	else {
		if ("http://www.w3.org/2000/svg" == i) l = l.replace(/xlink(H|:h)/, "h").replace(/sName$/, "s");
		else if ("width" != l && "height" != l && "href" != l && "list" != l && "form" != l && "tabIndex" != l && "download" != l && "rowSpan" != l && "colSpan" != l && "role" != l && "popover" != l && l in n) try {
			n[l] = null == u ? "" : u;
			break n;
		} catch (n) {}
		"function" == typeof u || (null == u || !1 === u && "-" != l[4] ? n.removeAttribute(l) : n.setAttribute(l, "popover" == l && 1 == u ? "" : u));
	}
}
function V(n) {
	return function(u) {
		if (this.l) {
			var t = this.l[u.type + n];
			if (null == u[c$1]) u[c$1] = h$1++;
			else if (u[c$1] < t[a$1]) return;
			return t(l$1.event ? l$1.event(u) : u);
		}
	};
}
function q(n, u, t, i, r, o, e, f, c, a) {
	var s, h, p, v, y, d, _, k, x, M, $, I, P, A, H, T, j = u.type;
	if (void 0 !== u.constructor) return null;
	128 & t.__u && (c = !!(32 & t.__u), o = [f = u.__e = t.__e]), (s = l$1.__b) && s(u);
	n: if ("function" == typeof j) {
		h = e.length;
		try {
			if (x = u.props, M = j.prototype && j.prototype.render, $ = (s = j.contextType) && i[s.__c], I = s ? $ ? $.props.value : s.__ : i, t.__c ? k = (p = u.__c = t.__c).__ = p.__E : (M ? u.__c = p = new j(x, I) : (u.__c = p = new C$1(x, I), p.constructor = j, p.render = Q), $ && $.sub(p), p.state || (p.state = {}), p.__n = i, v = p.__d = !0, p.__h = [], p._sb = []), M && null == p.__s && (p.__s = p.state), M && null != j.getDerivedStateFromProps && (p.__s == p.state && (p.__s = m$2({}, p.__s)), m$2(p.__s, j.getDerivedStateFromProps(x, p.__s))), y = p.props, d = p.state, p.__v = u, v) M && null == j.getDerivedStateFromProps && null != p.componentWillMount && p.componentWillMount(), M && null != p.componentDidMount && p.__h.push(p.componentDidMount);
			else {
				if (M && null == j.getDerivedStateFromProps && x !== y && null != p.componentWillReceiveProps && p.componentWillReceiveProps(x, I), u.__v == t.__v || !p.__e && null != p.shouldComponentUpdate && !1 === p.shouldComponentUpdate(x, p.__s, I)) {
					u.__v != t.__v && (p.props = x, p.state = p.__s, p.__d = !1), u.__e = t.__e, u.__k = t.__k, u.__k.some(function(n) {
						n && (n.__ = u);
					}), w$1.push.apply(p.__h, p._sb), p._sb = [], p.__h.length && e.push(p);
					break n;
				}
				null != p.componentWillUpdate && p.componentWillUpdate(x, p.__s, I), M && null != p.componentDidUpdate && p.__h.push(function() {
					p.componentDidUpdate(y, d, _);
				});
			}
			if (p.context = I, p.props = x, p.__P = n, p.__e = !1, P = l$1.__r, A = 0, M) p.state = p.__s, p.__d = !1, P && P(u), s = p.render(p.props, p.state, p.context), w$1.push.apply(p.__h, p._sb), p._sb = [];
			else do
				p.__d = !1, P && P(u), s = p.render(p.props, p.state, p.context), p.state = p.__s;
			while (p.__d && ++A < 25);
			p.state = p.__s, null != p.getChildContext && (i = m$2(m$2({}, i), p.getChildContext())), M && !v && null != p.getSnapshotBeforeUpdate && (_ = p.getSnapshotBeforeUpdate(y, d)), H = null != s && s.type === S && null == s.key ? E(s.props.children) : s, f = L(n, g(H) ? H : [H], u, t, i, r, o, e, f, c, a), p.base = u.__e, u.__u &= -161, p.__h.length && e.push(p), k && (p.__E = p.__ = null);
		} catch (n) {
			if (e.length = h, u.__v = null, c || null != o) {
				if (n.then) {
					for (u.__u |= c ? 160 : 128; f && 8 == f.nodeType && f.nextSibling;) f = f.nextSibling;
					null != o && (o[o.indexOf(f)] = null), u.__e = f;
				} else if (null != o) for (T = o.length; T--;) b(o[T]);
			} else u.__e = t.__e;
			u.__k ??= t.__k || [], n.then || B$1(u), l$1.__e(n, u, t);
		}
	} else null == o && u.__v == t.__v ? (u.__k = t.__k, u.__e = t.__e) : f = u.__e = G(t.__e, u, t, i, r, o, e, c, a);
	return (s = l$1.diffed) && s(u), 128 & u.__u ? void 0 : f;
}
function B$1(n) {
	n && (n.__c && (n.__c.__e = !0), n.__k && n.__k.some(B$1));
}
function D$1(n, u, t) {
	for (var i = 0; i < t.length; i++) J(t[i], t[++i], t[++i]);
	l$1.__c && l$1.__c(u, n), n.some(function(u) {
		try {
			n = u.__h, u.__h = [], n.some(function(n) {
				n.call(u);
			});
		} catch (n) {
			l$1.__e(n, u.__v);
		}
	});
}
function E(n) {
	return "object" != typeof n || null == n || n.__b > 0 ? n : g(n) ? n.map(E) : void 0 !== n.constructor ? null : m$2({}, n);
}
function G(u, t, i, r, o, e, f, c, a) {
	var s, h, p, v, y, w, _, m = i.props || d$1, k = t.props, x = t.type;
	if ("svg" == x ? o = "http://www.w3.org/2000/svg" : "math" == x ? o = "http://www.w3.org/1998/Math/MathML" : o || (o = "http://www.w3.org/1999/xhtml"), null != e) {
		for (s = 0; s < e.length; s++) if ((y = e[s]) && "setAttribute" in y == !!x && (x ? y.localName == x : 3 == y.nodeType)) {
			u = y, e[s] = null;
			break;
		}
	}
	if (null == u) {
		if (null == x) return document.createTextNode(k);
		u = document.createElementNS(o, x, k.is && k), c && (l$1.__m && l$1.__m(t, e), c = !1), e = null;
	}
	if (null == x) m === k || c && u.data == k || (u.data = k);
	else {
		if (e = "textarea" == x && null != k.defaultValue ? null : e && n$1.call(u.childNodes), !c && null != e) for (m = {}, s = 0; s < u.attributes.length; s++) m[(y = u.attributes[s]).name] = y.value;
		for (s in m) y = m[s], "dangerouslySetInnerHTML" == s ? p = y : "children" == s || s in k || "value" == s && "defaultValue" in k || "checked" == s && "defaultChecked" in k || N(u, s, null, y, o);
		for (s in k) y = k[s], "children" == s ? v = y : "dangerouslySetInnerHTML" == s ? h = y : "value" == s ? w = y : "checked" == s ? _ = y : c && "function" != typeof y || m[s] === y || N(u, s, y, m[s], o);
		if (h) c || p && (h.__html == p.__html || h.__html == u.innerHTML) || (u.innerHTML = h.__html), t.__k = [];
		else if (p && (u.innerHTML = ""), L("template" == t.type ? u.content : u, g(v) ? v : [v], t, i, r, "foreignObject" == x ? "http://www.w3.org/1999/xhtml" : o, e, f, e ? e[0] : i.__k && $(i, 0), c, a), null != e) for (s = e.length; s--;) b(e[s]);
		c && "textarea" != x || (s = "value", "progress" == x && null == w ? u.removeAttribute("value") : null != w && (w !== u[s] || "progress" == x && !w || "option" == x && w != m[s]) && N(u, s, w, m[s], o), s = "checked", null != _ && _ != u[s] && N(u, s, _, m[s], o));
	}
	return u;
}
function J(n, u, t) {
	try {
		if ("function" == typeof n) {
			var i = "function" == typeof n.__u;
			i && n.__u(), i && null == u || (n.__u = n(u));
		} else n.current = u;
	} catch (n) {
		l$1.__e(n, t);
	}
}
function K(n, u, t) {
	var i, r;
	if (l$1.unmount && l$1.unmount(n), (i = n.ref) && (i.current && i.current != n.__e || J(i, null, u)), null != (i = n.__c)) {
		if (i.componentWillUnmount) try {
			i.componentWillUnmount();
		} catch (n) {
			l$1.__e(n, u);
		}
		i.base = i.__P = i.__n = null;
	}
	if (i = n.__k) for (r = 0; r < i.length; r++) i[r] && K(i[r], u, t || "function" != typeof n.type);
	t || b(n.__e), n.__c = n.__ = n.__e = void 0;
}
function Q(n, l, u) {
	return this.constructor(n, u);
}
function R(u, t, i) {
	var r, o, e, f;
	t == document && (t = document.documentElement), l$1.__ && l$1.__(u, t), o = (r = "function" == typeof i) ? null : i && i.__k || t.__k, e = [], f = [], q(t, u = (!r && i || t).__k = k$1(S, null, [u]), o || d$1, d$1, t.namespaceURI, !r && i ? [i] : o ? null : t.firstChild ? n$1.call(t.childNodes) : null, e, !r && i ? i : o ? o.__e : t.firstChild, r, f), D$1(e, u, f), u.props.children = null;
}
n$1 = w$1.slice, l$1 = { __e: function(n, l, u, t) {
	for (var i, r, o; l = l.__;) if ((i = l.__c) && !i.__) try {
		if ((r = i.constructor) && null != r.getDerivedStateFromError && (i.setState(r.getDerivedStateFromError(n)), o = i.__d), null != i.componentDidCatch && (i.componentDidCatch(n, t || {}), o = i.__d), o) return i.__E = i;
	} catch (l) {
		n = l;
	}
	throw n;
} }, u$1 = 0, C$1.prototype.setState = function(n, l) {
	var u = null != this.__s && this.__s != this.state ? this.__s : this.__s = m$2({}, this.state);
	"function" == typeof n && (n = n(m$2({}, u), this.props)), n && m$2(u, n), null != n && this.__v && (l && this._sb.push(l), A$1(this));
}, C$1.prototype.forceUpdate = function(n) {
	this.__v && (this.__e = !0, n && this.__h.push(n), A$1(this));
}, C$1.prototype.render = S, i$1 = [], o$1 = "function" == typeof Promise ? Promise.prototype.then.bind(Promise.resolve()) : setTimeout, e$1 = function(n, l) {
	return n.__v.__b - l.__v.__b;
}, H.__r = 0, f$1 = Math.random().toString(8), c$1 = "__d" + f$1, a$1 = "__a" + f$1, s$1 = /(PointerCapture)$|Capture$/i, h$1 = 0, p$1 = V(!1), v$1 = V(!0);
//#endregion
//#region node_modules/htm/dist/htm.module.js
var n = function(t, s, r, e) {
	var u;
	s[0] = 0;
	for (var h = 1; h < s.length; h++) {
		var p = s[h++], a = s[h] ? (s[0] |= p ? 1 : 2, r[s[h++]]) : s[++h];
		3 === p ? e[0] = a : 4 === p ? e[1] = Object.assign(e[1] || {}, a) : 5 === p ? (e[1] = e[1] || {})[s[++h]] = a : 6 === p ? e[1][s[++h]] += a + "" : p ? (u = t.apply(a, n(t, a, r, ["", null])), e.push(u), a[0] ? s[0] |= 2 : (s[h - 2] = 0, s[h] = u)) : e.push(a);
	}
	return e;
};
var t$1 = /* @__PURE__ */ new Map();
function htm_module_default(s) {
	var r = t$1.get(this);
	return r || (r = /* @__PURE__ */ new Map(), t$1.set(this, r)), (r = n(this, r.get(s) || (r.set(s, r = function(n) {
		for (var t, s, r = 1, e = "", u = "", h = [0], p = function(n) {
			1 === r && (n || (e = e.replace(/^\s*\n\s*|\s*\n\s*$/g, ""))) ? h.push(0, n, e) : 3 === r && (n || e) ? (h.push(3, n, e), r = 2) : 2 === r && "..." === e && n ? h.push(4, n, 0) : 2 === r && e && !n ? h.push(5, 0, !0, e) : r >= 5 && ((e || !n && 5 === r) && (h.push(r, 0, e, s), r = 6), n && (h.push(r, n, 0, s), r = 6)), e = "";
		}, a = 0; a < n.length; a++) {
			a && (1 === r && p(), p(a));
			for (var l = 0; l < n[a].length; l++) t = n[a][l], 1 === r ? "<" === t ? (p(), h = [h], r = 3) : e += t : 4 === r ? "--" === e && ">" === t ? (r = 1, e = "") : e = t + e[0] : u ? t === u ? u = "" : e += t : "\"" === t || "'" === t ? u = t : ">" === t ? (p(), r = 1) : r && ("=" === t ? (r = 5, s = e, e = "") : "/" === t && (r < 5 || ">" === n[a][l + 1]) ? (p(), 3 === r && (h = h[0]), r = h, (h = h[0]).push(2, 0, r), r = 0) : " " === t || "	" === t || "\n" === t || "\r" === t ? (p(), r = 2) : e += t), 3 === r && "!--" === e && (r = 4, h = h[0]);
		}
		return p(), h;
	}(s)), r), arguments, [])).length > 1 ? r : r[0];
}
//#endregion
//#region node_modules/htm/preact/index.module.js
var m$1 = htm_module_default.bind(k$1);
//#endregion
//#region node_modules/preact/hooks/dist/hooks.module.js
var t;
var r;
var u;
var i;
var o = 0;
var f = [];
var c = l$1;
var e = c.__b;
var a = c.__r;
var v = c.diffed;
var l = c.__c;
var m = c.unmount;
var p = c.__;
function s(n, t) {
	c.__h && c.__h(r, n, o || t), o = 0;
	var u = r.__H || (r.__H = {
		__: [],
		__h: []
	});
	return n >= u.__.length && u.__.push({}), u.__[n];
}
function d(n) {
	return o = 1, y(D, n);
}
function y(n, u, i) {
	var o = s(t++, 2);
	if (o.t = n, !o.__c && (o.__ = [i ? i(u) : D(void 0, u), function(n) {
		var t = o.__N ? o.__N[0] : o.__[0], r = o.t(t, n);
		t !== r && (o.__N = [r, o.__[1]], o.__c.setState({}));
	}], o.__c = r, !r.__f)) {
		var f = function(n, t, r) {
			if (!o.__c.__H) return !0;
			var u = !1, i = o.__c.props !== n;
			if (o.__c.__H.__.some(function(n) {
				if (n.__N) {
					u = !0;
					var t = n.__[0];
					n.__ = n.__N, n.__N = void 0, t !== n.__[0] && (i = !0);
				}
			}), c) {
				var f = c.call(this, n, t, r);
				return u ? f || i : f;
			}
			return !u || i;
		};
		r.__f = !0;
		var c = r.shouldComponentUpdate, e = r.componentWillUpdate;
		r.componentWillUpdate = function(n, t, r) {
			if (this.__e) {
				var u = c;
				c = void 0, f(n, t, r), c = u;
			}
			e && e.call(this, n, t, r);
		}, r.shouldComponentUpdate = f;
	}
	return o.__N || o.__;
}
function h(n, u) {
	var i = s(t++, 3);
	!c.__s && C(i.__H, u) && (i.__ = n, i.u = u, r.__H.__h.push(i));
}
function _(n, u) {
	var i = s(t++, 4);
	!c.__s && C(i.__H, u) && (i.__ = n, i.u = u, r.__h.push(i));
}
function A(n) {
	return o = 5, T(function() {
		return { current: n };
	}, []);
}
function T(n, r) {
	var u = s(t++, 7);
	return C(u.__H, r) && (u.__ = n(), u.__H = r, u.__h = n), u.__;
}
function j() {
	for (var n; n = f.shift();) {
		var t = n.__H;
		if (n.__P && t) try {
			t.__h.some(z), t.__h.some(B), t.__h = [];
		} catch (r) {
			t.__h = [], c.__e(r, n.__v);
		}
	}
}
c.__b = function(n) {
	r = null, e && e(n);
}, c.__ = function(n, t) {
	n && t.__k && t.__k.__m && (n.__m = t.__k.__m), p && p(n, t);
}, c.__r = function(n) {
	a && a(n), t = 0;
	var i = (r = n.__c).__H;
	i && (u === r ? (i.__h = [], r.__h = [], i.__.some(function(n) {
		n.__N && (n.__ = n.__N), n.u = n.__N = void 0;
	})) : (i.__h.some(z), i.__h.some(B), i.__h = [], t = 0)), u = r;
}, c.diffed = function(n) {
	v && v(n);
	var t = n.__c;
	t && t.__H && (t.__H.__h.length && (1 !== f.push(t) && i === c.requestAnimationFrame || ((i = c.requestAnimationFrame) || w)(j)), t.__H.__.some(function(n) {
		n.u && (n.__H = n.u, n.u = void 0);
	})), u = r = null;
}, c.__c = function(n, t) {
	t.some(function(n) {
		try {
			n.__h.some(z), n.__h = n.__h.filter(function(n) {
				return !n.__ || B(n);
			});
		} catch (r) {
			t.some(function(n) {
				n.__h && (n.__h = []);
			}), t = [], c.__e(r, n.__v);
		}
	}), l && l(n, t);
}, c.unmount = function(n) {
	m && m(n);
	var t, r = n.__c;
	r && r.__H && (r.__H.__.some(function(n) {
		try {
			z(n);
		} catch (n) {
			t = n;
		}
	}), r.__H = void 0, t && c.__e(t, r.__v));
};
var k = "function" == typeof requestAnimationFrame;
function w(n) {
	var t, r = function() {
		clearTimeout(u), k && cancelAnimationFrame(t), setTimeout(n);
	}, u = setTimeout(r, 35);
	k && (t = requestAnimationFrame(r));
}
function z(n) {
	var t = r, u = n.__c;
	"function" == typeof u && (n.__c = void 0, u()), r = t;
}
function B(n) {
	var t = r;
	n.__c = n.__(), r = t;
}
function C(n, t) {
	return !n || n.length !== t.length || t.some(function(t, r) {
		return t !== n[r];
	});
}
function D(n, t) {
	return "function" == typeof t ? t(n) : t;
}
//#endregion
//#region web/src/machines.js
var COLORS = [
	"#80bfff",
	"#c4a0f5",
	"#91a4ee",
	"#ed9bc4",
	"#adc87f",
	"#edba83",
	"#65d5c0",
	"#d2bd79"
];
var machineName = (name) => name || "Unknown machine";
function machineColor(name) {
	let hash = 2166136261;
	for (const c of machineName(name)) hash = Math.imul(hash ^ c.codePointAt(0), 16777619);
	return COLORS[(hash >>> 0) % COLORS.length];
}
function machineList(nodes = [], recipients = []) {
	const all = new Map(nodes.map((n) => [machineName(n.name), {
		...n,
		name: machineName(n.name)
	}]));
	for (const r of recipients) {
		const name = machineName(r.node);
		if (!all.has(name)) all.set(name, {
			name,
			connected: false,
			missing: true
		});
	}
	return [...all.values()].map((n) => {
		const agents = recipients.filter((r) => machineName(r.node) === n.name);
		return {
			...n,
			total: agents.length,
			live: agents.filter((r) => r.pane_alive).length
		};
	}).sort((a, b) => Number(!!b.local) - Number(!!a.local) || a.name.localeCompare(b.name));
}
//#endregion
//#region web/src/shared.js
var POLL_MS = 2e3;
var PEEK_MS = 2e3;
var JSONH = { "content-type": "application/json" };
var FLAVOR_ICON = {
	claude: "✳",
	codex: "◇",
	pi: "π",
	hermes: "☿",
	generic: "▪"
};
var HARNESSES = Object.freeze({
	claude: {
		key: "claude",
		label: "Claude",
		color: "#d8905f",
		mark: "✳"
	},
	codex: {
		key: "codex",
		label: "Codex",
		color: "#56b4e9",
		mark: "◇"
	},
	pi: {
		key: "pi",
		label: "Pi",
		color: "#3cb44b",
		mark: "π"
	},
	hermes: {
		key: "hermes",
		label: "Hermes",
		color: "#e5c14f",
		mark: "☿"
	},
	generic: {
		key: "generic",
		label: "Generic",
		color: "#9aa1a8",
		mark: "▪"
	}
});
function harnessStyle(flavor) {
	return HARNESSES[String(flavor || "generic").toLowerCase()] || HARNESSES.generic;
}
function harnessChoices(recipients = []) {
	const generic = recipients.some((r) => r.pane_alive && harnessStyle(r.flavor).key === "generic");
	return Object.values(HARNESSES).filter((h) => h.key !== "generic" || generic);
}
function agentShown(r, machine, harness) {
	return (machine === null || machineName(r.node) === machine) && (harness === null || harnessStyle(r.flavor).key === harness);
}
function HarnessFilter({ recipients, harness, setHarness }) {
	return m$1`<span class="harness-filter" role="group" aria-label="Filter agents by harness">
    ${harnessChoices(recipients).map((h) => m$1`<button key=${h.key} type="button" class="harness-swatch"
      style=${`--harness:${h.color}`} aria-pressed=${harness === h.key} aria-label=${`Only ${h.label} agents`}
      title=${harness === h.key ? `Showing only ${h.label} agents. Click to show all.` : `Show only ${h.label} agents`}
      onClick=${() => setHarness(harness === h.key ? null : h.key)}>${h.mark}</button>`)}
  </span>`;
}
var WORKING_HALO = {
	color: "#9be879",
	fill: "rgba(155,232,121,.14)"
};
var STATE = {
	working: {
		cls: "working",
		word: "working",
		color: "var(--state-working)"
	},
	needs_attention: {
		cls: "attention",
		word: "needs attention",
		color: "var(--state-attention)"
	},
	idle: {
		cls: "idle",
		word: "idle",
		color: "var(--state-idle)"
	},
	unknown: {
		cls: "unknown",
		word: "unknown",
		color: "var(--state-unknown)"
	},
	stopped: {
		cls: "stopped",
		word: "stopped",
		color: "var(--state-stopped)"
	}
};
function agentStatus(r) {
	if (!r.pane_alive) return "stopped";
	const s = r.activity && r.activity.status;
	if (s && s !== "unknown") return s;
	return "unknown";
}
var ANIMAL_EMOJI = {
	otter: "🦦",
	badger: "🦡",
	panda: "🐼",
	raccoon: "🦝",
	hedgehog: "🦔",
	viper: "🐍",
	gecko: "🦎",
	newt: "🦎",
	salamander: "🦎",
	capybara: "🦫",
	manatee: "🦭",
	lemur: "🐒",
	kestrel: "🦅",
	magpie: "🐦‍⬛",
	ibis: "🦩",
	heron: "🪿",
	puffin: "🐧",
	narwhal: "🐳",
	axolotl: "🐟",
	quokka: "🐨",
	wombat: "🐨",
	dormouse: "🐁",
	shrew: "🐁",
	fennec: "🦊",
	mongoose: "🦦",
	stoat: "🦦",
	marten: "🦦",
	ferret: "🦦",
	ocelot: "🐆",
	pangolin: "🦎",
	tapir: "🐗",
	civet: "🐱"
};
function hue(name) {
	let h = 0;
	for (const c of name) h = (h * 31 + c.codePointAt(0)) % 360;
	return h;
}
function rel(ts, now) {
	const d = Math.max(0, now - ts);
	if (d < 50) return "just now";
	if (d < 3600) return `${Math.round(d / 60)}m ago`;
	if (d < 86400) return `${Math.round(d / 3600)}h ago`;
	return `${Math.round(d / 86400)}d ago`;
}
var SUMMARY_SOURCE = {
	agent: "said by the agent",
	title: "from its pane title"
};
function pairKey(a, b) {
	return [a, b].sort().join(" ");
}
var disp = (u) => u === "owner" ? m$1`<span class="owner-name">owner</span>` : u;
var focusHash = (u) => `#/agent/${encodeURIComponent(u)}`;
async function patchTask(id, patch) {
	try {
		const r = await fetch(`/tasks/${id}`, {
			method: "PATCH",
			headers: JSONH,
			body: JSON.stringify(patch)
		});
		if (r.ok) return { ok: true };
		return {
			ok: false,
			error: (await r.json().catch(() => null))?.detail?.error || `request failed (${r.status})`
		};
	} catch {
		return {
			ok: false,
			error: "Update not confirmed. Refresh the board before retrying."
		};
	}
}
function Avatar({ name, size }) {
	const base = name.replace(/-\d+$/, "");
	const emoji = ANIMAL_EMOJI[base];
	return m$1`<div class=${`hex ${size || ""}`} style=${`--hue: hsl(${hue(name)} 42% 58%)`}>
    ${emoji || m$1`<span class="mono2">${base.slice(0, 2)}</span>`}
  </div>`;
}
function MachineBadge({ node }) {
	return m$1`<span class="machine-badge" style=${`--machine:${machineColor(node)}`} title=${`Machine: ${machineName(node)}`}><span class="machine-mark" aria-hidden="true"></span>${machineName(node)}</span>`;
}
function Bee({ node, flavor, size = "", working = false }) {
	const harness = harnessStyle(flavor);
	return m$1`<svg class=${`agent-bee ${size}`} style=${`--machine:${machineColor(node)}`} viewBox="0 0 56 42" role="img" aria-label=${`${machineName(node)} machine, ${harness.label} harness${working ? ", working" : ""}`}>
    <title>${harness.label} harness: ${harness.mark} and stripes · ${machineName(node)}: body and border</title>
    ${working && m$1`<g class="bee-working-halo" style=${`--working:${WORKING_HALO.color}`}>
      <circle cx="27" cy="21" r="28" fill=${WORKING_HALO.fill} stroke=${WORKING_HALO.color} stroke-width="2.5" />
    </g>`}
    <ellipse cx="23" cy="10" rx="11" ry="6" fill="#f0e6d2" opacity=".65" transform="rotate(-25 23 10)" />
    <ellipse cx="23" cy="32" rx="11" ry="6" fill="#f0e6d2" opacity=".65" transform="rotate(25 23 32)" />
    <ellipse cx="26" cy="21" rx="19" ry="10" fill=${machineColor(node)} />
    <path d="M19 12v18M29 11v20" stroke="#16120c" stroke-width="7" />
    <path d="M19 12v18M29 11v20" stroke=${harness.color} stroke-width="4" />
    <circle cx="44" cy="21" r="6" fill="#16120c" /><circle cx="46" cy="19" r="1.3" fill="#f0e6d2" />
  </svg>`;
}
//#endregion
//#region web/src/quick-switch.js
function switchOptions(state, mode, query) {
	if (!state) return [];
	const teams = state.teams || [];
	const agents = state.recipients;
	let options;
	if (mode === "teams") options = teams.map((team) => {
		const members = agents.filter((a) => a.team_id === team.id).sort((a, b) => Number(b.pane_alive) - Number(a.pane_alive) || Number(b.user_id === team.queen) - Number(a.user_id === team.queen) || a.user_id.localeCompare(b.user_id));
		const target = members[0];
		return {
			id: `team-${team.id}`,
			name: team.name,
			target,
			detail: target ? `${members.filter((a) => a.pane_alive).length} live · opens ${target.user_id}${target.pane_alive ? "" : " (offline)"}` : "No registered agents",
			search: [team.name, ...members.map((a) => a.user_id)].join(" ")
		};
	});
	else options = agents.map((a) => {
		const team = teams.find((t) => t.id === a.team_id)?.name || "no team";
		return {
			id: `agent-${a.user_id}`,
			name: a.user_id,
			target: a,
			detail: `${team} · ${a.node || "unknown machine"} · ${a.pane_alive ? (a.activity?.status || "online").replaceAll("_", " ") : "offline"}`,
			search: [
				a.user_id,
				team,
				a.node,
				a.flavor,
				a.model
			].filter(Boolean).join(" ")
		};
	});
	const words = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
	return options.filter((o) => words.every((w) => o.search.toLowerCase().includes(w))).sort((a, b) => Number(!a.target) - Number(!b.target) || Number(!a.target?.pane_alive) - Number(!b.target?.pane_alive) || a.name.localeCompare(b.name));
}
function QuickSwitcher({ state, navigate }) {
	const [mode, setMode] = d(null);
	const [query, setQuery] = d("");
	const [selected, setSelected] = d(null);
	const dialog = A(null), input = A(null), previous = A(null);
	const mac = /Mac|iPhone|iPad/.test(navigator.platform);
	const shortcut = mac ? "⌘" : "Ctrl+";
	const open = (next) => {
		if (!state) return;
		if (!dialog.current?.open) previous.current = document.activeElement;
		setQuery("");
		setSelected(null);
		setMode(next);
	};
	const close = () => {
		dialog.current?.close();
		setMode(null);
	};
	_(() => {
		const onKey = (e) => {
			const platformModifier = mac ? e.metaKey && !e.ctrlKey : e.ctrlKey && !e.metaKey;
			if (e.isComposing || e.altKey || !platformModifier || e.code !== "KeyK") return;
			e.preventDefault();
			e.stopImmediatePropagation();
			if (!e.repeat) open(e.shiftKey ? "teams" : "agents");
		};
		addEventListener("keydown", onKey, true);
		return () => removeEventListener("keydown", onKey, true);
	});
	_(() => {
		if (mode) {
			if (!dialog.current.open) dialog.current.showModal();
			input.current?.focus();
		}
	}, [mode]);
	const options = switchOptions(state, mode, query);
	const enabled = options.filter((o) => o.target);
	const current = enabled.find((o) => o.id === selected) || enabled[0];
	_(() => {
		if (mode && current) document.getElementById(`switch-${current.id}`)?.scrollIntoView({ block: "nearest" });
	}, [mode, current?.id]);
	const choose = (option) => {
		if (!option?.target) return;
		close();
		navigate(option.target.user_id, previous.current);
	};
	const onKey = (e) => {
		e.stopPropagation();
		if (e.isComposing) return;
		if (e.key === "Escape") {
			e.preventDefault();
			close();
		}
		if (["ArrowDown", "ArrowUp"].includes(e.key)) {
			e.preventDefault();
			if (enabled.length) {
				const index = enabled.findIndex((o) => o.id === current?.id);
				setSelected(enabled[(index + (e.key === "ArrowDown" ? 1 : -1) + enabled.length) % enabled.length].id);
			}
		}
		if (e.key === "Enter" && e.target === input.current) {
			e.preventDefault();
			choose(current);
		}
	};
	return m$1`<div class="quick-switch-launchers">
    <button type="button" class="mini" disabled=${!state} onClick=${() => open("teams")} title=${`Switch teams (${shortcut}Shift+K)`}>teams <kbd>${shortcut}⇧K</kbd></button>
    <button type="button" class="mini" disabled=${!state} onClick=${() => open("agents")} title=${`Switch agents (${shortcut}K)`}>agents <kbd>${shortcut}K</kbd></button>
    <dialog class="quick-switch" ref=${dialog} aria-labelledby="switch-title" onKeyDown=${onKey}
      onCancel=${(e) => {
		e.preventDefault();
		close();
	}}>
      <div class="quick-switch-head"><h2 id="switch-title">${mode === "teams" ? "Switch team" : "Switch agent"}</h2>
        <button type="button" class="mini" onClick=${close}>close</button></div>
      <input ref=${input} type="search" aria-label=${mode === "teams" ? "Find team" : "Find agent"}
        role="combobox" aria-autocomplete="list" aria-expanded="true" aria-controls="switch-results"
        aria-activedescendant=${current ? `switch-${current.id}` : void 0}
        placeholder=${mode === "teams" ? "Search teams…" : "Search name, team, machine, or harness…"}
        value=${query} onInput=${(e) => {
		setQuery(e.target.value);
		setSelected(null);
	}} />
      <div id="switch-results" role="listbox" aria-label="Matches" class="quick-switch-results">
        ${options.map((o) => m$1`<div key=${o.id} id=${`switch-${o.id}`} role="option" aria-selected=${current?.id === o.id}
          aria-disabled=${!o.target} class=${`quick-switch-option ${current?.id === o.id ? "selected" : ""}`}
          onClick=${() => choose(o)}>
          ${o.target && m$1`<${Bee} node=${o.target.node} flavor=${o.target.flavor} size="small" working=${o.target.activity?.status === "working"} />`}
          <span><b>${o.name}</b><small>${o.detail}</small></span>
        </div>`)}
        ${!options.length && m$1`<p class="empty">No matches.</p>`}
      </div>
      <p class="quick-switch-help">↑ ↓ select · Enter open · Esc close</p>
    </dialog>
  </div>`;
}
//#endregion
//#region web/src/agent-history.js
function useAgentHistory(user) {
	const [history, setHistory] = d({
		messages: [],
		loaded: false,
		more: false,
		busy: false,
		error: ""
	});
	const older = A(() => {});
	h(() => {
		let active = true, polling = false, loadingOlder = false;
		let newest = null, oldest = null;
		const abort = new AbortController();
		const read = async (query) => {
			const response = await fetch(`/api/agents/${encodeURIComponent(user)}/messages?${query}`, { signal: abort.signal });
			if (!response.ok) throw Error("History unavailable");
			const page = await response.json();
			if (!Array.isArray(page.messages) || typeof page.has_more !== "boolean") throw Error("Invalid history");
			return page;
		};
		const merge = (page, initial = false, isOlder = false) => {
			if (!active) return;
			const ids = page.messages.map((m) => m.id);
			if (ids.length) {
				newest = Math.max(newest ?? 0, ...ids);
				oldest = Math.min(oldest ?? Infinity, ...ids);
			} else if (initial) newest = 0;
			setHistory((prev) => ({
				...prev,
				loaded: true,
				error: "",
				more: initial || isOlder ? page.has_more : prev.more,
				messages: [...new Map([...prev.messages, ...page.messages].map((m) => [m.id, m])).values()]
			}));
		};
		const poll = async () => {
			if (polling) return;
			polling = true;
			try {
				const initial = newest === null;
				let page = await read(initial ? "limit=300" : `after=${newest}&limit=300`);
				merge(page, initial);
				while (active && !initial && page.has_more) {
					page = await read(`after=${newest}&limit=300`);
					merge(page);
				}
			} catch {
				if (active) setHistory((prev) => ({
					...prev,
					error: "Could not load conversation history. Retrying…"
				}));
			} finally {
				polling = false;
			}
		};
		older.current = async () => {
			if (loadingOlder || oldest === null) return;
			loadingOlder = true;
			setHistory((prev) => ({
				...prev,
				busy: true
			}));
			try {
				merge(await read(`before=${oldest}&limit=300`), false, true);
			} catch {
				if (active) setHistory((prev) => ({
					...prev,
					error: "Could not load older messages. Please try again."
				}));
			} finally {
				loadingOlder = false;
				if (active) setHistory((prev) => ({
					...prev,
					busy: false
				}));
			}
		};
		poll();
		const timer = setInterval(poll, POLL_MS);
		return () => {
			active = false;
			abort.abort();
			clearInterval(timer);
		};
	}, [user]);
	return {
		...history,
		loadOlder: () => older.current()
	};
}
//#endregion
//#region web/src/task-trash.js
function TaskTrash({ task, refresh, onDeleted }) {
	const [busy, setBusy] = d(false);
	const [error, setError] = d("");
	const remove = async () => {
		if (!confirm(`Permanently trash task #${task.id}: ${task.title}? This cannot be undone. Agent conversations and working files will remain.`)) return;
		setBusy(true);
		setError("");
		try {
			const response = await fetch(`/tasks/${task.id}`, { method: "DELETE" });
			const body = await response.json();
			if (!response.ok) throw new Error(body.detail?.error || "Could not trash task.");
			onDeleted?.();
			refresh();
		} catch (err) {
			setError(`${err.message} Refresh to check the task before retrying.`);
		} finally {
			setBusy(false);
		}
	};
	return m$1`<span class="task-trash"><button type="button" class="mini danger" disabled=${busy}
    title=${`Permanently trash task #${task.id}`} onClick=${remove}>${busy ? "Trashing…" : "⌫ Trash"}</button>
    ${error && m$1`<span role="alert" class="tnote-err">${error}</span>`}</span>`;
}
//#endregion
//#region web/src/task-status.js
function TaskStatusActions({ task, refresh }) {
	const [editing, setEditing] = d(false);
	const [note, setNote] = d(task.note || "");
	const [busy, setBusy] = d(false);
	const [error, setError] = d("");
	const change = async (patch) => {
		setBusy(true);
		setError("");
		try {
			const result = await patchTask(task.id, patch);
			if (!result.ok) {
				setError(result.error);
				return;
			}
			setEditing(false);
			await refresh();
		} catch {
			setError("Could not update the task. Try again.");
		} finally {
			setBusy(false);
		}
	};
	const complete = () => {
		const verification = (editing ? note : task.note || "").trim();
		if (!verification) {
			setEditing(true);
			return;
		}
		change({
			status: "done",
			note: verification
		});
	};
	return m$1`<div class=${`task-status-actions ${editing ? "editing" : ""}`}>
    ${task.status === "done" ? m$1`<button type="button" class="mini" disabled=${busy}
          onClick=${() => change({ status: task.assignee || task.team_id ? "picked_up" : "open" })}>Reopen</button>` : m$1`${task.status === "open" && m$1`<button type="button" class="mini"
          disabled=${busy || !(task.assignee || task.team_id)}
          title=${task.assignee || task.team_id ? "Start work on this task" : "Assign this task first"}
          onClick=${() => change({ status: "picked_up" })}>Start work</button>`}
        <button type="button" class="mini" disabled=${busy || editing && !note.trim()}
          onClick=${complete}>${busy ? "Updating…" : "Complete task"}</button>`}
    ${editing && task.status !== "done" && m$1`<div class="task-verification">
      <label>Verification note <span aria-hidden="true">*</span>
        <textarea rows="3" value=${note} autofocus
          placeholder="How to use or verify the result, and where to look."
          onInput=${(e) => setNote(e.target.value)}></textarea>
      </label>
      <button type="button" class="mini" disabled=${busy}
        onClick=${() => {
		setEditing(false);
		setError("");
	}}>Cancel</button>
    </div>`}
    ${error && m$1`<span class="task-action-error" role="alert">${error}</span>`}
  </div>`;
}
//#endregion
//#region web/src/outcome.js
function structured(body) {
	return body !== null && typeof body === "object" && !Array.isArray(body);
}
function deliveryOutcome(httpOk, body) {
	if (!structured(body)) return {
		status: "uncertain",
		reason: "the server's answer could not be read"
	};
	const b = body;
	if (b.status === "delivered") return {
		status: "delivered",
		reason: null
	};
	if (b.status === "unknown") return {
		status: "unknown",
		reason: b.delivery_error || "result lost"
	};
	if (b.status === "failed") return {
		status: "failed",
		reason: b.delivery_error || "delivery failed"
	};
	const detail = structured(b.detail) ? b.detail : {};
	if (detail.status === "unknown") return {
		status: "unknown",
		reason: detail.error || detail.detail || "result lost"
	};
	if (!httpOk && (detail.error || b.error)) return {
		status: "failed",
		reason: detail.error || b.error
	};
	return {
		status: "uncertain",
		reason: "the server's answer was not recognised"
	};
}
function unansweredOutcome(err) {
	return {
		status: "uncertain",
		reason: err && err.message || "no answer from the server"
	};
}
function draftClientId(draft, retryOf, makeId) {
	return retryOf && retryOf.text === draft.text && retryOf.context === draft.context && JSON.stringify(retryOf.images || []) === JSON.stringify(draft.images || []) ? retryOf.clientId : makeId();
}
function spawnTarget(nodes, selected, harnesses) {
	const all = Array.isArray(nodes) ? nodes : [];
	all.find((n) => n.local);
	if (!selected) return {
		ok: true,
		remote: false,
		node: null,
		harnesses,
		reason: null
	};
	const n = all.find((x) => x.name === selected);
	if (!n) return {
		ok: false,
		remote: true,
		node: selected,
		harnesses: [],
		reason: `${selected} is no longer enrolled`
	};
	if (n.local) return {
		ok: true,
		remote: false,
		node: null,
		harnesses,
		reason: null
	};
	if (!n.connected) return {
		ok: false,
		remote: true,
		node: selected,
		harnesses: [],
		reason: `${selected} is not connected`
	};
	const offered = (harnesses || []).filter((h) => (n.harnesses || []).includes(h.flavor));
	if (offered.length === 0) return {
		ok: false,
		remote: true,
		node: selected,
		harnesses: [],
		reason: `${selected} reports no spawnable harness`
	};
	return {
		ok: true,
		remote: true,
		node: selected,
		harnesses: offered,
		reason: null
	};
}
function spawnOutcome(httpOk, body) {
	if (!structured(body)) return {
		status: "uncertain",
		reason: "the server's answer could not be read"
	};
	const b = body;
	if (b.launch === "ok" && b.user_id) return {
		status: "ok",
		reason: null,
		user: b.user_id
	};
	if (b.launch === "unknown") return {
		status: "unknown",
		reason: b.launch_error || "the launch command did not report back",
		user: b.user_id
	};
	const detail = structured(b.detail) ? b.detail : {};
	if (detail.status === "unknown") return {
		status: "unknown",
		reason: detail.detail || detail.error || "no report"
	};
	if (!httpOk && (detail.status === "failed" || detail.error || detail.detail || b.error)) return {
		status: "failed",
		reason: detail.detail || detail.error || b.error || "spawn failed"
	};
	return {
		status: "uncertain",
		reason: "the server's answer was not recognised"
	};
}
//#endregion
//#region web/src/use-media.js
var COMPACT_LAYOUT = "(max-width: 1000px), (max-width: 1200px) and (pointer: coarse)";
function useMedia(query) {
	const [matches, setMatches] = d(() => matchMedia(query).matches);
	h(() => {
		const media = matchMedia(query);
		const update = () => setMatches(media.matches);
		update();
		media.addEventListener("change", update);
		return () => media.removeEventListener("change", update);
	}, [query]);
	return matches;
}
//#endregion
//#region web/src/attachments.js
var attachmentLabel = (name) => name.includes(".file.") ? name.slice(name.indexOf(".file.") + 6) : "Image";
var isImage = (name) => /^[a-f0-9]{64}\.(png|jpg|gif|webp)$/.test(name);
var MAX_FILES = 10;
var MAX_BYTES = 10 * 1024 * 1024;
var hasFiles = (e) => [...e.dataTransfer?.types || []].includes("Files");
function useAttachments(files, setFiles, setStatus, scope) {
	const [uploading, setUploading] = d(0);
	const [dragging, setDragging] = d(false);
	const session = A(null);
	const filesRef = A(files);
	filesRef.current = files;
	h(() => {
		const current = {
			active: true,
			pending: 0
		};
		session.current = current;
		setUploading(0);
		return () => {
			current.active = false;
		};
	}, [scope]);
	const addFiles = async (incoming) => {
		const current = session.current;
		if (!current?.active) return;
		const batch = [...incoming || []];
		if (filesRef.current.length + current.pending + batch.length > MAX_FILES) {
			setStatus(`Up to ${MAX_FILES} attachments per task or message.`);
			return;
		}
		current.pending += batch.length;
		setUploading(current.pending);
		for (const file of batch) {
			if (!current.active) break;
			try {
				if (file.size > MAX_BYTES) throw Error("larger than 10 MB");
				const response = await fetch("/attachments", {
					method: "POST",
					headers: {
						"content-type": file.type || "application/octet-stream",
						"x-attachment-filename": encodeURIComponent(file.name || "attachment")
					},
					body: file
				});
				const body = await response.json();
				if (!response.ok || !body.name) throw Error(body.detail?.error || `upload failed (${response.status})`);
				if (current.active) {
					const next = [.../* @__PURE__ */ new Set([...filesRef.current, body.name])];
					filesRef.current = next;
					setFiles(next);
				}
			} catch (error) {
				if (current.active) setStatus(`${file.name || "File"} not added: ${error.message}`);
			} finally {
				current.pending--;
				if (current.active) setUploading(current.pending);
			}
		}
	};
	return {
		uploading,
		dragging,
		addFiles,
		remove: (name) => setFiles((prev) => prev.filter((x) => x !== name)),
		onPaste: (e) => {
			const pasted = [...e.clipboardData?.files || []];
			if (pasted.length) {
				e.preventDefault();
				addFiles(pasted);
			}
		},
		dropProps: {
			onDragOver: (e) => {
				if (hasFiles(e)) {
					e.preventDefault();
					setDragging(true);
				}
			},
			onDragLeave: (e) => {
				if (!e.currentTarget.contains(e.relatedTarget)) setDragging(false);
			},
			onDrop: (e) => {
				if (hasFiles(e)) {
					e.preventDefault();
					setDragging(false);
					addFiles(e.dataTransfer.files);
				}
			}
		}
	};
}
function AttachmentLink({ name }) {
	const [missing, setMissing] = d(false);
	if (missing) return m$1`<span class="image-expired">Attachment unavailable</span>`;
	return m$1`<a class=${isImage(name) ? "image-link" : "file-link"} href=${`/attachments/${name}`} target="_blank" rel="noopener" title=${isImage(name) ? "Open image" : `Download ${attachmentLabel(name)}`}>
    ${isImage(name) ? m$1`<img src=${`/attachments/${name}`} alt="Attached image" loading="lazy" onError=${() => setMissing(true)} />` : m$1`<span aria-hidden="true">▤</span> ${attachmentLabel(name)} <span aria-hidden="true">↓</span>`}
  </a>`;
}
function AttachmentList({ files = [] }) {
	return files.length > 0 && m$1`<div class="attachment-list">${files.map((name) => m$1`<${AttachmentLink} key=${name} name=${name} />`)}</div>`;
}
function AttachmentPicker({ files, controls, disabled = false }) {
	const input = A(null);
	return m$1`<div class="attachment-picker">
    <div class="attachment-tools"><button type="button" class="mini" disabled=${disabled} onClick=${() => input.current?.click()}>+ attach files</button><span>Paste or drop files · 10 MB each · up to 10</span></div>
    <input ref=${input} type="file" multiple hidden disabled=${disabled} onChange=${(e) => {
		controls.addFiles(e.target.files);
		e.target.value = "";
	}} />
    ${(files.length > 0 || controls.uploading > 0) && m$1`<div class="compose-images">${files.map((name) => m$1`<figure key=${name} class="compose-image">
      <${AttachmentLink} name=${name} /><button type="button" class="remove" disabled=${disabled} onClick=${() => controls.remove(name)} aria-label=${`Remove ${attachmentLabel(name)}`}>×</button>
    </figure>`)}${controls.uploading > 0 && m$1`<span role="status">Uploading ${controls.uploading}…</span>`}</div>`}
  </div>`;
}
//#endregion
//#region web/src/hive.js
var TASK_CELL_RADIUS = 18;
var TASK_CELL_CLEARANCE = 22;
var DANCE_MS = 7e3;
function taskCellClearsTeams(point, boxes) {
	return boxes.every((box) => point.x <= box.x - TASK_CELL_CLEARANCE || point.x >= box.x + box.w + TASK_CELL_CLEARANCE || point.y <= box.y - TASK_CELL_CLEARANCE || point.y >= box.y + box.h + TASK_CELL_CLEARANCE);
}
function placeTaskCell(ideal, boxes, occupied, width) {
	const bounds = {
		minX: TASK_CELL_CLEARANCE,
		maxX: Math.max(TASK_CELL_CLEARANCE, width - TASK_CELL_CLEARANCE),
		minY: TASK_CELL_CLEARANCE,
		maxY: 260 - TASK_CELL_CLEARANCE
	};
	const candidate = (x, y) => ({
		x: Math.max(bounds.minX, Math.min(bounds.maxX, x)),
		y: Math.max(bounds.minY, Math.min(bounds.maxY, y))
	});
	const usable = (point) => taskCellClearsTeams(point, boxes) && occupied.every((other) => Math.hypot(point.x - other.x, point.y - other.y) >= 34);
	const start = candidate(ideal.x, ideal.y);
	if (usable(start)) return start;
	const step = 17;
	const limit = Math.hypot(width, 260);
	for (let radius = step; radius <= limit; radius += step) {
		const samples = Math.max(12, Math.ceil(Math.PI * 2 * radius / step));
		for (let i = 0; i < samples; i++) {
			const angle = -Math.PI / 2 + i * Math.PI * 2 / samples;
			const point = candidate(ideal.x + Math.cos(angle) * radius, ideal.y + Math.sin(angle) * radius);
			if (usable(point)) return point;
		}
	}
	return start;
}
function CompactBees({ state, machine, harness = null }) {
	const agents = (state.recipients || []).filter((r) => r.pane_alive && agentShown(r, machine, harness));
	return m$1`<nav class="compact-hive" aria-label="Live agents">
    <div class="compact-hive-heading"><span>${agents.length} live agents</span><span>Tap a bee to open</span></div>
    <div class="bee-grid">${agents.map((r) => {
		const status = agentStatus(r);
		const st = STATE[status] || STATE.unknown;
		const harness = harnessStyle(r.flavor);
		return m$1`<a key=${r.user_id} class="bee-tile" href=${focusHash(r.user_id)} style=${`--machine:${machineColor(r.node)}`}>
        <${Bee} node=${r.node} flavor=${r.flavor} working=${status === "working"} />
        <span class="bee-name">${r.user_id}</span>
        <span class="bee-machine">${machineName(r.node)}</span>
        <span class="bee-state"><span class=${`status ${st.cls}`} aria-hidden="true"></span>${st.word} · ${harness.mark} ${harness.label}</span>
      </a>`;
	})}</div>
    ${!agents.length && m$1`<p class="compact-hive-empty">No live ${harness ? `${harnessStyle(harness).label} ` : ""}agents${machine ? ` on ${machine}` : ""}. Offline agents are listed under their team.</p>`}
  </nav>`;
}
function HiveTaskDetail({ task, state, refresh, onClose }) {
	const [busy, setBusy] = d(false);
	const [error, setError] = d("");
	const assign = async (e) => {
		const value = e.target.value;
		setBusy(true);
		setError("");
		try {
			const result = await patchTask(task.id, value.startsWith("t:") ? { team_id: Number(value.slice(2)) } : {
				assignee: value || null,
				team_id: null
			});
			if (!result.ok) setError(result.error);
			else refresh();
		} catch {
			setError("Could not assign task. Try again.");
		} finally {
			setBusy(false);
		}
	};
	const agents = [.../* @__PURE__ */ new Set([...(state.recipients || []).map((r) => r.user_id), ...task.assignee ? [task.assignee] : []])];
	return m$1`<section class="hive-task-detail" aria-label=${`Task #${task.id} details`}>
    <header><h3>#${task.id} · ${task.title}</h3>
      <button type="button" class="mini" onClick=${onClose}>Collapse</button></header>
    <p>${task.status.replaceAll("_", " ")} · ${task.assignee || "unassigned"}${task.team_id ? ` · team ${(state.teams || []).find((t) => t.id === task.team_id)?.name || task.team_id}` : ""}</p>
    ${task.description && m$1`<p class="task-description">${task.description}</p>`}
    ${task.depends_on?.length > 0 && m$1`<p>Depends on ${task.depends_on.map((id) => `#${id}`).join(", ")}</p>`}
    ${task.worktree && m$1`<p>Worktree: ${task.worktree_node || ""} ${task.worktree}</p>`}
    <${AttachmentList} files=${task.attachments} />
    ${task.note && m$1`<p class="task-description">${task.note}</p>`}
    <label class="hive-task-assignment">Assign to
      <select aria-label=${`Assign task #${task.id}`} value=${task.team_id ? `t:${task.team_id}` : task.assignee || ""} disabled=${busy || task.status === "done"} onChange=${assign}>
        <option value="">unassigned</option>
        <optgroup label="Teams">${(state.teams || []).map((t) => m$1`<option value=${`t:${t.id}`}>${t.name}</option>`)}</optgroup>
        <optgroup label="Agents">${agents.map((a) => m$1`<option value=${a}>${a}</option>`)}</optgroup>
      </select>
    </label>
    ${error && m$1`<p role="alert">${error}</p>`}
    <${TaskStatusActions} task=${task} refresh=${refresh} />
    <${TaskTrash} task=${task} refresh=${refresh} onDeleted=${onClose} />
  </section>`;
}
function HiveView({ state, refresh, machine, harness = null, setHarness = () => {}, compactBody = null }) {
	const compact = useMedia(COMPACT_LAYOUT);
	const [selectedTask, setSelectedTask] = d(null);
	const taskDetail = (state.tasks || []).find((t) => t.id === selectedTask);
	const machineRef = A(machine);
	machineRef.current = machine;
	const harnessRef = A(harness);
	harnessRef.current = harness;
	const canvasRef = A(null);
	const stateRef = A(state);
	const beesRef = A(/* @__PURE__ */ new Map());
	const streaksRef = A([]);
	const pendingRef = A([]);
	const lastSeenRef = A(null);
	const hoverRef = A(null);
	const taskHoverRef = A(null);
	const taskCellsRef = A([]);
	const taskStatusesRef = A(null);
	const pendingShipmentsRef = A([]);
	const shipmentsRef = A([]);
	const dragTaskRef = A(null);
	const dragBeeRef = A(null);
	const dragPointRef = A(null);
	const dropTargetRef = A(null);
	const dropTeamRef = A(null);
	const dragBoxRef = A(null);
	const teamBoxesRef = A([]);
	const drawRef = A(null);
	const danceRef = A(null);
	const [dropStatus, setDropStatus] = d("");
	stateRef.current = state;
	const legendHarnesses = harnessChoices(state.recipients);
	const messages = state.messages || [];
	const maxId = Math.max(0, ...messages.map((m) => m.id));
	if (lastSeenRef.current === null) lastSeenRef.current = maxId;
	else if (maxId > lastSeenRef.current) {
		if (!compact) pendingRef.current.push(...messages.filter((m) => m.id > lastSeenRef.current).slice(-8));
		lastSeenRef.current = maxId;
	}
	const taskSnapshot = new Map((state.tasks || []).map((t) => [t.id, t]));
	if (taskStatusesRef.current === null) taskStatusesRef.current = taskSnapshot;
	else {
		for (const task of state.tasks || []) {
			const before = taskStatusesRef.current.get(task.id);
			if (!compact && before && before.status !== "done" && task.status === "done") pendingShipmentsRef.current.push(task);
		}
		taskStatusesRef.current = taskSnapshot;
	}
	h(() => {
		if (compact) {
			pendingRef.current = [];
			pendingShipmentsRef.current = [];
			return;
		}
		const canvas = canvasRef.current;
		const ctx = canvas.getContext("2d");
		const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
		let frame = 0;
		let cssWidth = 0;
		let lastDraw = 0;
		const POS_KEY = "agent-swarm-hive-team-pos";
		const teamPos = /* @__PURE__ */ new Map();
		try {
			for (const [k, v] of Object.entries(JSON.parse(localStorage.getItem(POS_KEY) || "{}"))) if (v && Number.isFinite(v.x) && Number.isFinite(v.y)) teamPos.set(Number(k), {
				x: v.x,
				y: v.y
			});
		} catch {}
		const savePos = () => {
			const known = new Set((stateRef.current.teams || []).map((t) => t.id));
			const obj = {};
			for (const [id, p] of teamPos) if (known.has(id)) obj[id] = {
				x: Math.round(p.x),
				y: Math.round(p.y)
			};
			try {
				localStorage.setItem(POS_KEY, JSON.stringify(obj));
			} catch {}
		};
		const hex = (x, y, radius, fill, stroke) => {
			ctx.beginPath();
			for (let i = 0; i < 6; i++) {
				const a = i * Math.PI / 3;
				const px = x + Math.cos(a) * radius;
				const py = y + Math.sin(a) * radius;
				i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
			}
			ctx.closePath();
			ctx.fillStyle = fill;
			ctx.fill();
			ctx.strokeStyle = stroke;
			ctx.lineWidth = 1;
			ctx.stroke();
		};
		const token = (task, x, y) => {
			hex(x, y, 8, "rgba(242,169,59,.15)", "#b97f27");
			ctx.fillStyle = "#f2a93b";
			ctx.font = "8px ui-monospace, monospace";
			ctx.textAlign = "center";
			ctx.textBaseline = "middle";
			ctx.fillText(`#${task.id}`, x, y + .5);
		};
		const ensureSize = () => {
			const width = Math.max(1, canvas.clientWidth);
			const dpr = devicePixelRatio || 1;
			if (width !== cssWidth || canvas.width !== Math.round(width * dpr)) {
				cssWidth = width;
				canvas.width = Math.round(width * dpr);
				canvas.height = Math.round(260 * dpr);
			}
			ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
			return width;
		};
		const point = (a, b, c, u) => {
			const v = 1 - u;
			return {
				x: v * v * a.x + 2 * v * u * c.x + u * u * b.x,
				y: v * v * a.y + 2 * v * u * c.y + u * u * b.y
			};
		};
		const draw = (now, still = false) => {
			const width = ensureSize();
			const data = stateRef.current;
			const running = (data.recipients || []).filter((r) => r.pane_alive);
			const live = new Set(running.map((r) => r.user_id));
			const bees = beesRef.current;
			for (const name of bees.keys()) if (!live.has(name)) bees.delete(name);
			ctx.clearRect(0, 0, width, 260);
			const center = {
				x: width / 2,
				y: 118
			};
			const ownerNode = {
				x: width / 2,
				y: 235
			};
			const done = (data.tasks || []).filter((t) => t.status === "done").length;
			const doneX = width - 28;
			hex(doneX - 7, 34, 11, "rgba(143,191,111,.07)", "#567546");
			hex(doneX, 28, 14, "rgba(143,191,111,.15)", "#8fbf6f");
			ctx.fillStyle = "#8fbf6f";
			ctx.textAlign = "right";
			ctx.textBaseline = "middle";
			ctx.fillText(`shipped · ${done}`, doneX - 24, 28);
			const teamsList = data.teams || [];
			const teamById = new Map(teamsList.map((t) => [t.id, t]));
			const teamColor = (name, alpha) => `hsl(${hue(name)} 45% 62% / ${alpha})`;
			const grouped = [...running].sort((a, b) => (a.team_id && teamById.has(a.team_id) ? a.team_id : 1e9) - (b.team_id && teamById.has(b.team_id) ? b.team_id : 1e9));
			const positioned = new Set([...teamPos.keys()].filter((id) => teamById.has(id)));
			const posOf = (id) => {
				const p = teamPos.get(id);
				return {
					x: Math.max(56, Math.min(width - 56, p.x)),
					y: Math.max(58, Math.min(202, p.y))
				};
			};
			const clusterCount = /* @__PURE__ */ new Map();
			for (const r of grouped) if (r.team_id && positioned.has(r.team_id)) clusterCount.set(r.team_id, (clusterCount.get(r.team_id) || 0) + 1);
			const looseList = grouped.filter((r) => !(r.team_id && positioned.has(r.team_id)));
			const looseIndex = new Map(looseList.map((r, i) => [r.user_id, i]));
			const clusterSeen = /* @__PURE__ */ new Map();
			const homes = grouped.map((r) => {
				if (r.team_id && positioned.has(r.team_id)) {
					const pos = posOf(r.team_id);
					const count = clusterCount.get(r.team_id);
					const j = clusterSeen.get(r.team_id) || 0;
					clusterSeen.set(r.team_id, j + 1);
					const cols = Math.min(3, count);
					const rows = Math.ceil(count / cols);
					const row = Math.floor(j / cols);
					const inRow = row === rows - 1 ? count - row * cols : cols;
					return {
						x: pos.x + (j % cols - (inRow - 1) / 2) * 58,
						y: pos.y + (row - (rows - 1) / 2) * 46
					};
				}
				const i = looseIndex.get(r.user_id);
				const angle = Math.PI + i / Math.max(1, looseList.length) * Math.PI * 2;
				return {
					x: center.x + Math.cos(angle) * Math.min(width * .36, 330),
					y: 132 + Math.sin(angle) * 67
				};
			});
			teamBoxesRef.current = [];
			{
				const bounds = /* @__PURE__ */ new Map();
				grouped.forEach((r, i) => {
					if (!r.team_id || !teamById.has(r.team_id)) return;
					const h = homes[i];
					const b = bounds.get(r.team_id) || {
						minX: h.x,
						maxX: h.x,
						minY: h.y,
						maxY: h.y
					};
					b.minX = Math.min(b.minX, h.x);
					b.maxX = Math.max(b.maxX, h.x);
					b.minY = Math.min(b.minY, h.y);
					b.maxY = Math.max(b.maxY, h.y);
					bounds.set(r.team_id, b);
				});
				let emptyX = 12;
				for (const t of teamsList) {
					const b = bounds.get(t.id);
					const pos = positioned.has(t.id) ? posOf(t.id) : null;
					const box = b ? {
						x: b.minX - 44,
						y: b.minY - 40,
						w: b.maxX - b.minX + 88,
						h: b.maxY - b.minY + 90
					} : pos ? {
						x: pos.x - 47,
						y: pos.y - 22,
						w: 94,
						h: 44
					} : {
						x: emptyX,
						y: 28,
						w: 94,
						h: 44
					};
					if (!b && !pos) emptyX += 104;
					box.x = Math.max(4, box.x);
					box.y = Math.max(24, box.y);
					box.w = Math.min(box.w, width - box.x - 4);
					box.h = Math.min(box.h, 254 - box.y);
					teamBoxesRef.current.push({
						id: t.id,
						name: t.name,
						queen: t.queen,
						...box
					});
				}
				const draggingSomething = dragTaskRef.current !== null || dragBeeRef.current;
				for (const box of teamBoxesRef.current) {
					const over = draggingSomething && dropTeamRef.current === box.id;
					const moving = dragBoxRef.current === box.id;
					ctx.save();
					ctx.strokeStyle = teamColor(box.name, over || moving ? .95 : .4);
					ctx.lineWidth = over || moving ? 2 : 1;
					ctx.setLineDash(over || moving ? [] : [5, 4]);
					ctx.beginPath();
					ctx.roundRect(box.x, box.y, box.w, box.h, 12);
					ctx.stroke();
					if (over || moving) {
						ctx.fillStyle = teamColor(box.name, over ? .08 : .05);
						ctx.beginPath();
						ctx.roundRect(box.x, box.y, box.w, box.h, 12);
						ctx.fill();
					}
					ctx.restore();
					ctx.fillStyle = teamColor(box.name, .95);
					ctx.font = "9px ui-monospace, monospace";
					ctx.textAlign = "left";
					ctx.textBaseline = "alphabetic";
					ctx.fillText(box.queen ? `${box.name} · ♛ ${box.queen}` : box.name, box.x + 8, box.y + 11);
				}
			}
			const waiting = (data.tasks || []).filter((t) => t.status !== "done" && (!t.assignee || !live.has(t.assignee)));
			const carriedCount = (data.tasks || []).filter((t) => t.status !== "done" && t.assignee && live.has(t.assignee)).length;
			const visible = waiting.slice(0, 15);
			const cols = Math.min(5, Math.max(1, Math.ceil(Math.sqrt(visible.length || 1))));
			const rows = Math.ceil(visible.length / cols);
			const cellX = 38, cellY = 34;
			taskCellsRef.current = [];
			if (dragTaskRef.current === null && !dragBeeRef.current && dragBoxRef.current === null) {
				ctx.fillStyle = "#a89878";
				ctx.font = "10px ui-monospace, monospace";
				ctx.textAlign = "center";
				ctx.textBaseline = "middle";
				ctx.fillText(`task comb · ${waiting.length} waiting · ${carriedCount} carried`, center.x, 17);
			}
			const doneIds = new Set((data.tasks || []).filter((t) => t.status === "done").map((t) => t.id));
			const occupiedTaskCells = [];
			visible.forEach((task, i) => {
				const col = i % cols, row = Math.floor(i / cols);
				const { x, y } = placeTaskCell({
					x: center.x + (col - (cols - 1) / 2) * cellX,
					y: center.y - (rows - 1) * cellY / 2 + row * cellY + (col % 2 ? cellY / 2 : 0)
				}, teamBoxesRef.current, occupiedTaskCells, width);
				occupiedTaskCells.push({
					x,
					y
				});
				const stranded = task.assignee && !live.has(task.assignee);
				const team = task.team_id && teamById.get(task.team_id) || null;
				const blocked = (task.depends_on || []).some((d) => !doneIds.has(d));
				taskCellsRef.current.push({
					x,
					y,
					task,
					stranded,
					team,
					blocked
				});
			});
			const cellById = new Map(taskCellsRef.current.map((c) => [c.task.id, c]));
			ctx.save();
			ctx.strokeStyle = "rgba(242,169,59,.3)";
			ctx.lineWidth = 1;
			for (const cell of taskCellsRef.current) for (const dep of cell.task.depends_on || []) {
				const from = cellById.get(dep);
				if (!from) continue;
				ctx.beginPath();
				ctx.moveTo(from.x, from.y);
				ctx.lineTo(cell.x, cell.y);
				ctx.stroke();
			}
			ctx.restore();
			for (const cell of taskCellsRef.current) {
				const { x, y, task, stranded, team, blocked } = cell;
				const lifted = dragPointRef.current && dragTaskRef.current === task.id;
				if (lifted) ctx.globalAlpha = .3;
				ctx.save();
				if (blocked) ctx.setLineDash([3, 3]);
				hex(x, y, TASK_CELL_RADIUS, stranded ? "rgba(224,108,85,.10)" : team ? teamColor(team.name, .12) : "rgba(242,169,59,.12)", stranded ? "#e06c55" : team ? teamColor(team.name, .8) : "#b97f27");
				ctx.restore();
				ctx.fillStyle = stranded ? "#e06c55" : "#f2a93b";
				ctx.font = "9px ui-monospace, monospace";
				ctx.textAlign = "center";
				ctx.textBaseline = "middle";
				ctx.fillText(`#${task.id}`, x, y + .5);
				if (lifted) ctx.globalAlpha = 1;
			}
			if (waiting.length > visible.length) {
				ctx.fillStyle = "#a89878";
				ctx.font = "9px ui-monospace, monospace";
				ctx.textAlign = "center";
				ctx.textBaseline = "middle";
				ctx.fillText(`+${waiting.length - visible.length} more`, center.x, 202);
			}
			hex(ownerNode.x, ownerNode.y, 8, "rgba(242,169,59,.09)", "#b97f27");
			ctx.fillStyle = "#f2a93b";
			ctx.font = "9px ui-monospace, monospace";
			ctx.textAlign = "center";
			ctx.textBaseline = "alphabetic";
			ctx.fillText("owner", ownerNode.x, 253);
			const beeData = grouped.map((r, i) => {
				const name = r.user_id;
				const seed = hue(name);
				const harness = harnessStyle(r.flavor);
				const mine = (data.tasks || []).filter((t) => t.assignee === name && t.status !== "done").sort((a, b) => (a.status === "picked_up" ? -1 : 1) - (b.status === "picked_up" ? -1 : 1) || b.updated_at - a.updated_at);
				const picked = mine.find((t) => t.status === "picked_up");
				const assigned = !picked && mine.find((t) => t.status === "open");
				const primary = picked || assigned;
				const extras = mine.filter((t) => !primary || t.id !== primary.id);
				const phase = seed / 57;
				const working = agentStatus(r) === "working";
				const busy = !!picked || working;
				const speed = busy ? 2.5 : 1;
				const clustered = r.team_id && positioned.has(r.team_id);
				const amp = (busy ? 26 : 18) * (clustered ? .55 : 1);
				const q = still ? 0 : now / 8e3 * Math.PI * 2 * speed + phase;
				return {
					r,
					name,
					seed,
					harness,
					x: homes[i].x + (still ? 0 : Math.sin(q) * amp),
					y: homes[i].y + (still ? 0 : Math.sin(q * 1.7 + phase) * amp * .55),
					dx: still ? 1 : Math.cos(q),
					dy: still ? 0 : Math.cos(q * 1.7 + phase) * .94,
					q,
					picked,
					assigned,
					primary,
					extras,
					working,
					busy
				};
			});
			for (const bee of beeData) {
				for (const box of teamBoxesRef.current) {
					if (bee.r.team_id === box.id) continue;
					const m = 14;
					if (bee.x <= box.x - m || bee.x >= box.x + box.w + m || bee.y <= box.y - m || bee.y >= box.y + box.h + m) continue;
					const out = [
						{
							d: bee.x - (box.x - m),
							x: box.x - m,
							y: bee.y
						},
						{
							d: box.x + box.w + m - bee.x,
							x: box.x + box.w + m,
							y: bee.y
						},
						{
							d: bee.y - (box.y - m),
							x: bee.x,
							y: box.y - m
						},
						{
							d: box.y + box.h + m - bee.y,
							x: bee.x,
							y: box.y + box.h + m
						}
					].reduce((a, b) => a.d <= b.d ? a : b);
					bee.x = out.x;
					bee.y = out.y;
				}
				bee.x = Math.max(16, Math.min(width - 16, bee.x));
				bee.y = Math.max(34, Math.min(bee.picked || bee.working ? 208 : 224, bee.y));
			}
			const dance = danceRef.current;
			if (dance && !still) {
				const u = (now - dance.start) / DANCE_MS;
				if (u >= 1) danceRef.current = null;
				else if (u >= 0) {
					const ease = (v) => v * v * (3 - 2 * v);
					const mix = ease(Math.min(1, u / .15, (1 - u) / .15));
					const rx = Math.min(width * .38, 300);
					const loop = (t) => {
						const s = Math.sin(t), c = Math.cos(t), k = 1 + s * s;
						return {
							x: center.x + rx * c / k,
							y: 128 + rx * .62 * s * c / k
						};
					};
					ctx.save();
					ctx.strokeStyle = `rgba(242,169,59,${.28 * mix})`;
					ctx.setLineDash([2, 5]);
					ctx.beginPath();
					for (let k = 0; k <= 96; k++) {
						const p = loop(k / 96 * Math.PI * 2);
						k ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y);
					}
					ctx.stroke();
					ctx.restore();
					beeData.forEach((bee, i) => {
						const t = u * Math.PI * 4 + i / (beeData.length + .5) * Math.PI * 2;
						const a = loop(t), b = loop(t + .01);
						const tx = b.x - a.x, ty = b.y - a.y;
						const len = Math.hypot(tx, ty) || 1;
						const middle = Math.exp(-(((a.x - center.x) / 60) ** 2));
						const shimmy = Math.sin(now / 35) * 7 * middle;
						const fx = a.x - ty / len * shimmy, fy = a.y + tx / len * shimmy;
						bee.x += (fx - bee.x) * mix;
						bee.y += (fy - bee.y) * mix;
						if (mix > .5) {
							bee.dx = tx;
							bee.dy = ty;
						}
						bee.dancing = true;
					});
				}
			}
			for (const bee of beeData) {
				const { r, name, harness, x, y, dx, dy, q, picked, assigned, primary, extras, working, busy, dancing } = bee;
				const doing = r.summaries && r.summaries[0];
				bees.set(name, {
					x,
					y,
					task: primary,
					node: machineName(r.node),
					harness: harness.key,
					doing: doing && doing.text
				});
				ctx.save();
				if (!agentShown(r, machineRef.current, harnessRef.current)) ctx.globalAlpha = .18;
				if (assigned) token(assigned, x + 22, y + Math.sin(q * .8) * 3);
				const bearing = Math.atan2(dy, dx);
				ctx.save();
				ctx.translate(x, y);
				ctx.rotate(bearing);
				if (working) {
					ctx.save();
					ctx.fillStyle = WORKING_HALO.fill;
					ctx.strokeStyle = WORKING_HALO.color;
					ctx.lineWidth = 2.5;
					ctx.shadowColor = WORKING_HALO.color;
					ctx.shadowBlur = 12;
					ctx.beginPath();
					ctx.arc(0, 0, 24, 0, Math.PI * 2);
					ctx.fill();
					ctx.stroke();
					ctx.restore();
				}
				const flap = still ? 0 : Math.sin(now / 1e3 * (dancing ? 60 : busy ? 44 : 30)) * .35;
				ctx.fillStyle = "rgba(240,230,210,.5)";
				ctx.beginPath();
				ctx.ellipse(-2, -7, 6, 3, -.45 - flap, 0, Math.PI * 2);
				ctx.fill();
				ctx.beginPath();
				ctx.ellipse(-2, 7, 6, 3, .45 + flap, 0, Math.PI * 2);
				ctx.fill();
				ctx.fillStyle = machineColor(r.node);
				ctx.beginPath();
				ctx.ellipse(0, 0, 12, 6, 0, 0, Math.PI * 2);
				ctx.fill();
				ctx.fillStyle = "#16120c";
				ctx.fillRect(-5, -6, 4.5, 12);
				ctx.fillRect(1, -6, 4.5, 12);
				ctx.fillStyle = harness.color;
				ctx.fillRect(-4, -6, 2.5, 12);
				ctx.fillRect(2, -6, 2.5, 12);
				ctx.fillStyle = "#16120c";
				ctx.beginPath();
				ctx.arc(11, 0, 3.5, 0, Math.PI * 2);
				ctx.fill();
				ctx.restore();
				if (picked) token(picked, x, y + 16);
				extras.slice(0, 4).forEach((task, j) => {
					const a = -1.15 + j * .75;
					token(task, x + Math.cos(a) * 25, y + Math.sin(a) * 22);
				});
				if (extras.length > 4) {
					ctx.fillStyle = "#a89878";
					ctx.font = "8px ui-monospace, monospace";
					ctx.textAlign = "center";
					ctx.textBaseline = "middle";
					ctx.fillText(`+${extras.length - 4}`, x + 29, y + 12);
				}
				const labelY = y + (picked ? 35 : working ? 34 : 19);
				ctx.font = "10px ui-monospace, monospace";
				ctx.textBaseline = "alphabetic";
				const markGap = 3;
				const markW = ctx.measureText(harness.mark).width;
				const shortName = name.length > 20 ? `${name.slice(0, 19)}…` : name;
				const nameW = ctx.measureText(shortName).width;
				const labelLeft = x - (markW + markGap + nameW) / 2;
				ctx.textAlign = "left";
				ctx.fillStyle = harness.color;
				ctx.fillText(harness.mark, labelLeft, labelY);
				ctx.fillStyle = "#a89878";
				ctx.fillText(shortName, labelLeft + markW + markGap, labelY);
				ctx.textAlign = "center";
				ctx.font = "8px ui-monospace, monospace";
				ctx.fillStyle = machineColor(r.node);
				ctx.fillText(machineName(r.node), x, labelY + 11);
				const attention = r.activity && r.activity.status === "needs_attention";
				if (attention) {
					ctx.fillStyle = "#f2a93b";
					ctx.font = "bold 13px ui-monospace, monospace";
					ctx.textBaseline = "alphabetic";
					ctx.fillText("!", x, y - 14);
				}
				const myTeam = r.team_id && teamById.get(r.team_id) || null;
				if (myTeam && myTeam.queen === name) {
					ctx.fillStyle = "#f2a93b";
					ctx.font = "11px ui-monospace, monospace";
					ctx.textAlign = "center";
					ctx.textBaseline = "alphabetic";
					ctx.fillText("♛", x, y - (attention ? 26 : 14));
				}
				ctx.restore();
			}
			if (dragTaskRef.current !== null && dragPointRef.current) {
				const dragged = (data.tasks || []).find((t) => t.id === dragTaskRef.current);
				if (dragged) token(dragged, dragPointRef.current.x, dragPointRef.current.y);
			}
			const dragBee = dragBeeRef.current && bees.get(dragBeeRef.current);
			if (dragBee && dragPointRef.current) {
				const p = dragPointRef.current;
				const draggedRecipient = grouped.find((r) => r.user_id === dragBeeRef.current);
				ctx.save();
				ctx.strokeStyle = "rgba(240,230,210,.3)";
				ctx.setLineDash([3, 4]);
				ctx.beginPath();
				ctx.moveTo(dragBee.x, dragBee.y);
				ctx.lineTo(p.x, p.y);
				ctx.stroke();
				ctx.restore();
				ctx.save();
				ctx.globalAlpha = .85;
				ctx.fillStyle = machineColor(draggedRecipient?.node);
				ctx.beginPath();
				ctx.ellipse(p.x, p.y, 12, 6, 0, 0, Math.PI * 2);
				ctx.fill();
				ctx.fillStyle = harnessStyle(draggedRecipient?.flavor).color;
				ctx.fillRect(p.x - 4, p.y - 6, 2.5, 12);
				ctx.fillRect(p.x + 2, p.y - 6, 2.5, 12);
				ctx.restore();
			}
			const dropLabel = (label, ax, ay) => {
				ctx.font = "11px ui-monospace, monospace";
				const labelW = ctx.measureText(label).width + 14;
				const lx = Math.max(5, Math.min(width - labelW - 5, ax - labelW / 2));
				const ly = Math.max(5, ay);
				ctx.fillStyle = "#241c11";
				ctx.beginPath();
				ctx.roundRect(lx, ly, labelW, 21, 6);
				ctx.fill();
				ctx.strokeStyle = "#f2a93b";
				ctx.stroke();
				ctx.fillStyle = "#f0e6d2";
				ctx.textAlign = "left";
				ctx.textBaseline = "middle";
				ctx.fillText(label, lx + 7, ly + 11);
			};
			const banner = (text) => {
				ctx.fillStyle = "#f2a93b";
				ctx.font = "11px ui-monospace, monospace";
				ctx.textAlign = "center";
				ctx.textBaseline = "alphabetic";
				ctx.fillText(text, width / 2, 18);
			};
			const targetBox = dropTeamRef.current != null && teamBoxesRef.current.find((b) => b.id === dropTeamRef.current);
			const dropTarget = dropTargetRef.current && bees.get(dropTargetRef.current);
			if (dragTaskRef.current && dropTarget) {
				ctx.save();
				ctx.strokeStyle = "#f2a93b";
				ctx.lineWidth = 2;
				ctx.shadowColor = "rgba(242,169,59,.8)";
				ctx.shadowBlur = 13;
				ctx.beginPath();
				ctx.arc(dropTarget.x, dropTarget.y, 24, 0, Math.PI * 2);
				ctx.stroke();
				ctx.restore();
				dropLabel(`assign #${dragTaskRef.current} to ${dropTargetRef.current}`, dropTarget.x, Math.max(5, dropTarget.y - 43));
			} else if (dragTaskRef.current && targetBox) dropLabel(`assign #${dragTaskRef.current} to team ${targetBox.name}`, targetBox.x + targetBox.w / 2, Math.max(5, targetBox.y - 26));
			else if (dragTaskRef.current) banner(`drop task #${dragTaskRef.current} on a bee or a team`);
			else if (dragBeeRef.current && targetBox) dropLabel(`move ${dragBeeRef.current} to team ${targetBox.name}`, targetBox.x + targetBox.w / 2, Math.max(5, targetBox.y - 26));
			else if (dragBeeRef.current) {
				const r = grouped.find((x) => x.user_id === dragBeeRef.current);
				const home = r && r.team_id && teamById.get(r.team_id);
				banner(home ? `release to take ${dragBeeRef.current} out of team ${home.name}` : `drop ${dragBeeRef.current} on a team`);
			} else if (dragBoxRef.current !== null) {
				const moving = teamBoxesRef.current.find((b) => b.id === dragBoxRef.current);
				if (moving) banner(`release to place team ${moving.name}`);
			}
			const endpoint = (name) => name === "owner" ? ownerNode : bees.get(name) || ownerNode;
			if (!still && pendingRef.current.length) {
				const born = now;
				streaksRef.current.push(...pendingRef.current.splice(0, 8).map((m) => ({
					born,
					a: { ...endpoint(m.sender) },
					b: { ...endpoint(m.recipient) },
					id: m.id
				})));
			} else if (still) pendingRef.current.length = 0;
			streaksRef.current = streaksRef.current.filter((s) => now - s.born < 900);
			if (!still) for (const s of streaksRef.current) {
				const u = Math.min(1, (now - s.born) / 900);
				const c = {
					x: (s.a.x + s.b.x) / 2,
					y: (s.a.y + s.b.y) / 2 - 40
				};
				for (let i = 9; i >= 0; i--) {
					const p = point(s.a, s.b, c, Math.max(0, u - i * .025));
					ctx.fillStyle = `rgba(242,169,59,${(10 - i) / 13})`;
					ctx.beginPath();
					ctx.arc(p.x, p.y, i ? 1.2 : 2.5, 0, Math.PI * 2);
					ctx.fill();
				}
			}
			if (!still && pendingShipmentsRef.current.length) {
				const born = now;
				shipmentsRef.current.push(...pendingShipmentsRef.current.splice(0).map((task) => ({
					born,
					task,
					a: { ...bees.get(task.assignee) || ownerNode },
					b: {
						x: doneX,
						y: 28
					}
				})));
			} else if (still) pendingShipmentsRef.current.length = 0;
			shipmentsRef.current = shipmentsRef.current.filter((s) => now - s.born < 1100);
			if (!still) for (const shipment of shipmentsRef.current) {
				const u = Math.min(1, (now - shipment.born) / 1100);
				const c = {
					x: (shipment.a.x + shipment.b.x) / 2,
					y: Math.min(shipment.a.y, shipment.b.y) - 45
				};
				const p = point(shipment.a, shipment.b, c, u);
				ctx.save();
				ctx.globalAlpha = Math.min(1, (1 - u) * 2.4);
				token(shipment.task, p.x, p.y);
				ctx.restore();
			}
			const hovered = hoverRef.current && bees.get(hoverRef.current);
			if (hovered) {
				const said = hovered.doing || hovered.task && hovered.task.title;
				const title = said ? ` · ${said.length > 70 ? `${said.slice(0, 69)}…` : said}` : "";
				const harnessLabel = harnessStyle(hovered.harness).label;
				const label = `${hoverRef.current} · ${hovered.node} · ${harnessLabel}${title}`;
				ctx.font = "10px ui-monospace, monospace";
				const w = ctx.measureText(label).width + 12;
				const tx = Math.max(4, Math.min(width - w - 4, hovered.x - w / 2));
				const ty = Math.max(4, hovered.y - 31);
				ctx.fillStyle = "#241c11";
				ctx.beginPath();
				ctx.roundRect(tx, ty, w, 19, 5);
				ctx.fill();
				ctx.strokeStyle = "#3a2d1a";
				ctx.stroke();
				ctx.fillStyle = "#f0e6d2";
				ctx.textAlign = "left";
				ctx.textBaseline = "middle";
				ctx.fillText(label, tx + 6, ty + 10);
			}
			const taskCell = taskHoverRef.current;
			if (!hovered && taskCell) {
				const task = taskCell.task;
				const stateLabel = taskCell.stranded ? `assigned to stopped ${task.assignee}` : taskCell.team ? `team ${taskCell.team.name}` : "waiting";
				const blockedLabel = taskCell.blocked ? ` · blocked (after ${(task.depends_on || []).map((d) => `#${d}`).join(" ")})` : "";
				const label = `#${task.id} · ${task.title} · ${stateLabel}${blockedLabel} · click to expand · drag to assign`;
				ctx.font = "10px ui-monospace, monospace";
				const w = Math.min(width - 16, ctx.measureText(label).width + 12);
				const tx = Math.max(8, Math.min(width - w - 8, taskCell.x - w / 2));
				const ty = Math.min(232, taskCell.y + 25);
				ctx.fillStyle = "#241c11";
				ctx.beginPath();
				ctx.roundRect(tx, ty, w, 19, 5);
				ctx.fill();
				ctx.strokeStyle = taskCell.stranded ? "#e06c55" : "#b97f27";
				ctx.stroke();
				ctx.fillStyle = "#f0e6d2";
				ctx.textAlign = "left";
				ctx.textBaseline = "middle";
				ctx.fillText(label, tx + 6, ty + 10, w - 12);
			}
		};
		drawRef.current = draw;
		const at = (e) => {
			const r = canvas.getBoundingClientRect();
			return {
				x: e.clientX - r.left,
				y: e.clientY - r.top
			};
		};
		const hit = (e) => {
			const p = at(e);
			return [...beesRef.current].find(([, b]) => Math.hypot(p.x - b.x, p.y - b.y) < 24)?.[0] || null;
		};
		const hitTask = (e) => {
			const p = at(e);
			return taskCellsRef.current.find((cell) => Math.hypot(p.x - cell.x, p.y - cell.y) < 20) || null;
		};
		const hitTeam = (e) => {
			const p = at(e);
			return teamBoxesRef.current.find((b) => p.x >= b.x && p.x <= b.x + b.w && p.y >= b.y && p.y <= b.y + b.h) || null;
		};
		const taskId = (e) => {
			const raw = e.dataTransfer?.getData("application/x-agent-swarm-task") || e.dataTransfer?.getData("text/plain");
			return /^\d+$/.test(raw || "") ? Number(raw) : null;
		};
		const clearDrop = () => {
			dragTaskRef.current = null;
			dragBeeRef.current = null;
			dragPointRef.current = null;
			dropTargetRef.current = null;
			dropTeamRef.current = null;
			dragBoxRef.current = null;
			canvas.style.cursor = "default";
			if (reduced) draw(performance.now(), true);
		};
		const teamCenter = (id) => {
			const stored = teamPos.get(id);
			if (stored) return stored;
			const members = (stateRef.current.recipients || []).filter((r) => r.team_id === id && r.pane_alive).map((r) => beesRef.current.get(r.user_id)).filter(Boolean);
			if (members.length) return {
				x: members.reduce((s, b) => s + b.x, 0) / members.length,
				y: members.reduce((s, b) => s + b.y, 0) / members.length
			};
			const box = teamBoxesRef.current.find((b) => b.id === id);
			return box ? {
				x: box.x + box.w / 2,
				y: box.y + box.h / 2
			} : null;
		};
		const assign = async (id, assignee) => {
			const task = (stateRef.current.tasks || []).find((t) => t.id === id);
			if (!task || task.status === "done") {
				setDropStatus(`Task #${id} cannot be assigned by drag.`);
				return;
			}
			if (task.assignee === assignee) {
				setDropStatus(`#${id} is already assigned to ${assignee}.`);
				return;
			}
			try {
				if (!(await fetch(`/tasks/${id}`, {
					method: "PATCH",
					headers: JSONH,
					body: JSON.stringify({ assignee })
				})).ok) throw new Error("assignment failed");
				setDropStatus(`Assigned #${id} to ${assignee}.`);
				refresh();
			} catch {
				setDropStatus(`Could not assign #${id}; task was not changed.`);
			}
		};
		const assignTeam = async (id, box) => {
			const task = (stateRef.current.tasks || []).find((t) => t.id === id);
			if (!task || task.status === "done") {
				setDropStatus(`Task #${id} cannot be assigned by drag.`);
				return;
			}
			if (task.team_id === box.id) {
				setDropStatus(`#${id} is already assigned to team ${box.name}.`);
				return;
			}
			try {
				if (!(await fetch(`/tasks/${id}`, {
					method: "PATCH",
					headers: JSONH,
					body: JSON.stringify({ team_id: box.id })
				})).ok) throw new Error("assignment failed");
				setDropStatus(`Assigned #${id} to team ${box.name}.`);
				refresh();
			} catch {
				setDropStatus(`Could not assign #${id}; task was not changed.`);
			}
		};
		const setBeeTeam = async (user, teamId, doneLabel) => {
			try {
				if (!(await fetch(`/agents/${encodeURIComponent(user)}/team`, {
					method: "POST",
					headers: JSONH,
					body: JSON.stringify({ team_id: teamId })
				})).ok) throw new Error("move failed");
				setDropStatus(doneLabel);
				refresh();
			} catch {
				setDropStatus(`Could not move ${user}.`);
			}
		};
		let press = null;
		let suppressClick = false;
		const pointerDown = (e) => {
			if (e.button !== 0) return;
			const bee = hit(e);
			if (bee) {
				press = {
					bee,
					start: at(e),
					moved: false
				};
				canvas.setPointerCapture(e.pointerId);
				return;
			}
			const cell = hitTask(e);
			if (cell) {
				press = {
					id: cell.task.id,
					start: at(e),
					moved: false
				};
				canvas.setPointerCapture(e.pointerId);
				return;
			}
			const box = hitTeam(e);
			if (!box) return;
			const p = at(e);
			const c = teamCenter(box.id) || {
				x: box.x + box.w / 2,
				y: box.y + box.h / 2
			};
			press = {
				boxId: box.id,
				start: p,
				off: {
					x: c.x - p.x,
					y: c.y - p.y
				},
				moved: false
			};
			canvas.setPointerCapture(e.pointerId);
		};
		const pointerMove = (e) => {
			if (!press) return;
			const p = at(e);
			if (!press.moved && Math.hypot(p.x - press.start.x, p.y - press.start.y) < 5) return;
			press.moved = true;
			hoverRef.current = null;
			taskHoverRef.current = null;
			if (press.boxId != null) {
				dragBoxRef.current = press.boxId;
				teamPos.set(press.boxId, {
					x: p.x + press.off.x,
					y: p.y + press.off.y
				});
				canvas.style.cursor = "grabbing";
				if (reduced) draw(performance.now(), true);
				return;
			}
			dragPointRef.current = p;
			if (press.bee) {
				dragBeeRef.current = press.bee;
				const box = hitTeam(e);
				dropTeamRef.current = box ? box.id : null;
				canvas.style.cursor = "grabbing";
			} else {
				dragTaskRef.current = press.id;
				dropTargetRef.current = hit(e);
				const box = dropTargetRef.current ? null : hitTeam(e);
				dropTeamRef.current = box ? box.id : null;
				canvas.style.cursor = dropTargetRef.current || dropTeamRef.current != null ? "copy" : "grabbing";
			}
			if (reduced) draw(performance.now(), true);
		};
		const pointerUp = async (e) => {
			if (!press) return;
			const { id, bee, boxId, moved } = press;
			press = null;
			if (!moved) return;
			suppressClick = true;
			if (boxId != null) {
				savePos();
				clearDrop();
				return;
			}
			const targetBee = hit(e);
			const box = hitTeam(e);
			clearDrop();
			if (bee) {
				const r = (stateRef.current.recipients || []).find((x) => x.user_id === bee);
				const teams = stateRef.current.teams || [];
				const current = r && teams.find((t) => t.id === r.team_id);
				if (box && (!current || current.id !== box.id)) await setBeeTeam(bee, box.id, `Moved ${bee} to team ${box.name}.`);
				else if (!box && current) await setBeeTeam(bee, null, `Removed ${bee} from team ${current.name}.`);
				return;
			}
			if (targetBee) await assign(id, targetBee);
			else if (box) await assignTeam(id, box);
		};
		const pointerCancel = () => {
			press = null;
			clearDrop();
		};
		const move = (e) => {
			if (press) return;
			hoverRef.current = hit(e);
			taskHoverRef.current = hoverRef.current ? null : hitTask(e);
			const overBox = !hoverRef.current && !taskHoverRef.current && hitTeam(e);
			canvas.style.cursor = hoverRef.current ? "pointer" : taskHoverRef.current || overBox ? "grab" : "default";
			if (reduced) draw(performance.now(), true);
		};
		const leave = () => {
			if (press) return;
			hoverRef.current = null;
			taskHoverRef.current = null;
			if (dragTaskRef.current) clearDrop();
			else {
				canvas.style.cursor = "default";
				if (reduced) draw(performance.now(), true);
			}
		};
		const click = (e) => {
			if (suppressClick) {
				suppressClick = false;
				return;
			}
			const name = hit(e);
			if (name) {
				location.hash = focusHash(name);
				return;
			}
			const cell = hitTask(e);
			if (cell) setSelectedTask((id) => id === cell.task.id ? null : cell.task.id);
		};
		const dragOver = (e) => {
			const id = taskId(e);
			if (id === null) return;
			e.preventDefault();
			e.dataTransfer.dropEffect = "move";
			dragTaskRef.current = id;
			dropTargetRef.current = hit(e);
			const box = dropTargetRef.current ? null : hitTeam(e);
			dropTeamRef.current = box ? box.id : null;
			canvas.style.cursor = dropTargetRef.current || dropTeamRef.current != null ? "copy" : "not-allowed";
			if (reduced) draw(performance.now(), true);
		};
		const dragLeave = (e) => {
			if (e.target === canvas) clearDrop();
		};
		const drop = async (e) => {
			const id = taskId(e);
			const assignee = hit(e);
			const box = hitTeam(e);
			e.preventDefault();
			clearDrop();
			if (id === null) return;
			if (assignee) await assign(id, assignee);
			else if (box) await assignTeam(id, box);
		};
		window.__hive = {
			bees: () => beesRef.current,
			teamBoxes: () => teamBoxesRef.current,
			taskCells: () => taskCellsRef.current,
			dancing: () => danceRef.current !== null
		};
		canvas.addEventListener("mousemove", move);
		canvas.addEventListener("mouseleave", leave);
		canvas.addEventListener("click", click);
		canvas.addEventListener("pointerdown", pointerDown);
		canvas.addEventListener("pointermove", pointerMove);
		canvas.addEventListener("pointerup", pointerUp);
		canvas.addEventListener("pointercancel", pointerCancel);
		canvas.addEventListener("dragover", dragOver);
		canvas.addEventListener("dragleave", dragLeave);
		canvas.addEventListener("drop", drop);
		canvas.addEventListener("dragend", clearDrop);
		window.addEventListener("dragend", clearDrop);
		const resize = new ResizeObserver(() => {
			if (reduced) draw(performance.now(), true);
		});
		resize.observe(canvas);
		if (reduced) draw(performance.now(), true);
		else {
			const tick = (now) => {
				if (!document.hidden && now - lastDraw >= 32) {
					draw(now);
					lastDraw = now;
				}
				frame = requestAnimationFrame(tick);
			};
			frame = requestAnimationFrame(tick);
		}
		return () => {
			resize.disconnect();
			cancelAnimationFrame(frame);
			drawRef.current = null;
			delete window.__hive;
			canvas.removeEventListener("mousemove", move);
			canvas.removeEventListener("mouseleave", leave);
			canvas.removeEventListener("click", click);
			canvas.removeEventListener("pointerdown", pointerDown);
			canvas.removeEventListener("pointermove", pointerMove);
			canvas.removeEventListener("pointerup", pointerUp);
			canvas.removeEventListener("pointercancel", pointerCancel);
			canvas.removeEventListener("dragover", dragOver);
			canvas.removeEventListener("dragleave", dragLeave);
			canvas.removeEventListener("drop", drop);
			canvas.removeEventListener("dragend", clearDrop);
			window.removeEventListener("dragend", clearDrop);
		};
	}, [compact]);
	h(() => {
		if (matchMedia("(prefers-reduced-motion: reduce)").matches && drawRef.current) drawRef.current(performance.now(), true);
	}, [
		state,
		machine,
		harness
	]);
	return m$1`<div class="hive-panel">${compact ? compactBody || m$1`<${CompactBees} state=${state} machine=${machine} harness=${harness} />` : m$1`<div class="hive-scroll"><canvas ref=${canvasRef} tabindex="0"
    aria-label="Live activity. Bee body color and the machine name below each bee identify its machine, matching the machine selector. Stripe color and the symbol beside the agent name identify its harness. Drag a comb cell or a task card onto a bee or a team outline to assign the task; drag a bee into or out of a team outline to change its team; drag a team outline by its empty space to move the whole team somewhere else. Bees outside a team are kept out of team outlines. The task assignee select and the sidebar team boxes are the keyboard and touch alternatives."></canvas></div>`}
    <div class="harness-legend" aria-label="Bee harness legend">
      <span class="legend-title">Body = machine · stripes + symbol = harness</span>
      <span class="working-halo-key" style=${`--working:${WORKING_HALO.color}`}><span aria-hidden="true"></span>Green halo = working</span>
      ${legendHarnesses.map((h) => compact ? m$1`<span class="harness-key" key=${h.key}>
            <span class="harness-swatch" style=${`--harness:${h.color}`}>${h.mark}</span>${h.label}</span>` : m$1`<button type="button" class="harness-key" key=${h.key} aria-pressed=${harness === h.key}
            title=${harness === h.key ? "Click to show all harnesses" : `Highlight only ${h.label} agents`}
            onClick=${() => setHarness(harness === h.key ? null : h.key)}>
            <span class="harness-swatch" style=${`--harness:${h.color}`}>${h.mark}</span>${h.label}</button>`)}
      ${!compact && !matchMedia("(prefers-reduced-motion: reduce)").matches && m$1`<button type="button" class="hive-dance"
        title="Every bee flies a figure eight for a few seconds"
        onClick=${() => {
		if (!danceRef.current) danceRef.current = { start: performance.now() };
	}}>🐝 waggle dance</button>`}
    </div>
    <div class="hive-task-picker"><label>Expand task <select value=${selectedTask ?? ""}
      onChange=${(e) => setSelectedTask(e.target.value ? Number(e.target.value) : null)}>
      <option value="">${compact ? "Choose a task…" : "Click a honeycomb or choose a task…"}</option>
      ${(state.tasks || []).filter((t) => t.status !== "done" || t.id === selectedTask).map((t) => m$1`<option value=${t.id}>#${t.id} · ${t.title}</option>`)}
    </select></label></div>
    ${taskDetail && m$1`<${HiveTaskDetail} key=${taskDetail.id} task=${taskDetail} state=${state} refresh=${refresh} onClose=${() => setSelectedTask(null)} />`}
    <span class="sr-only" aria-live="polite">${dropStatus}</span></div>`;
}
//#endregion
//#region web/src/tabs.js
function forwardShortcuts(frame) {
	let win;
	try {
		win = frame.contentWindow;
		win.document;
	} catch {
		return;
	}
	win.addEventListener("keydown", (e) => {
		if (!(e.altKey || e.ctrlKey || e.metaKey)) return;
		const copy = new KeyboardEvent("keydown", {
			key: e.key,
			code: e.code,
			altKey: e.altKey,
			ctrlKey: e.ctrlKey,
			metaKey: e.metaKey,
			shiftKey: e.shiftKey,
			repeat: e.repeat,
			cancelable: true
		});
		if (!window.dispatchEvent(copy)) e.preventDefault();
	});
}
function TabView({ name, tabs }) {
	if (!tabs.includes(name)) return m$1`<div class="empty">No tab named <b>${name}</b>. Tabs come from the hub's
      <code>AGENT_SWARM_TABS</code> setting, e.g. <code>usage=http://127.0.0.1:8531</code>.</div>`;
	const src = `/tabs/${encodeURIComponent(name)}/`;
	return m$1`<section class="tab-view">
    <div class="tab-bar"><h2>${name}</h2><a class="mini" href=${src} target="_blank" rel="noopener">open alone ↗</a></div>
    <iframe key=${name} class="tab-frame" src=${src} title=${name} onLoad=${(e) => forwardShortcuts(e.currentTarget)}></iframe>
  </section>`;
}
//#endregion
//#region web/src/views.js
var TAB_ROUTE = "#/tab/";
var tabHash = (name) => `${TAB_ROUTE}${encodeURIComponent(name)}`;
function stepView(hash, views, by) {
	return views[(Math.max(0, views.findIndex((v) => v !== "#/" && (hash === v || hash.startsWith(`${v}?`)))) + by + views.length) % views.length];
}
//#endregion
//#region web/src/agent-chips.js
function agentChips(agentCount, recipients, selected) {
	const live = new Set(recipients.filter((r) => r.pane_alive).map((r) => r.user_id));
	const counts = new Map([...agentCount].filter(([a]) => live.has(a) || a === selected));
	if (selected && !counts.has(selected)) counts.set(selected, 0);
	return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}
//#endregion
//#region web/src/history.js
var HISTORY_ROUTE = "#/tasks";
var STATUSES = [
	["", "all"],
	["open", "open"],
	["picked_up", "picked up"],
	["done", "done"]
];
function historyHash({ q = "", status = "", agent = "", sort = "newest" } = {}) {
	const p = new URLSearchParams();
	if (q) p.set("q", q);
	if (status) p.set("status", status);
	if (agent) p.set("agent", agent);
	if (sort === "oldest") p.set("sort", "oldest");
	const s = p.toString();
	return s ? `${HISTORY_ROUTE}?${s}` : HISTORY_ROUTE;
}
function parseHash(hash) {
	const i = hash.indexOf("?");
	const p = new URLSearchParams(i < 0 ? "" : hash.slice(i + 1));
	return {
		q: p.get("q") || "",
		status: p.get("status") || "",
		agent: p.get("agent") || "",
		sort: p.get("sort") === "oldest" ? "oldest" : "newest"
	};
}
function taskRecords(tasks, teams) {
	const teamName = new Map((teams || []).map((t) => [t.id, t.name]));
	return tasks.map((t) => ({
		key: `task:${t.id}`,
		kind: "task",
		id: t.id,
		status: t.status,
		ts: t.created_at,
		agents: t.assignee ? [t.assignee] : [],
		fields: {
			title: t.title || "",
			description: t.description || "",
			note: t.note || "",
			assignee: t.assignee || "",
			worktree: t.worktree || "",
			team: teamName.get(t.team_id) || ""
		},
		src: t
	}));
}
function statusRecords(recipients) {
	return (recipients || []).flatMap((r) => (r.summaries || []).map((s, i) => ({
		key: `status:${r.user_id}:${s.ts}:${i}`,
		kind: "status",
		ts: s.ts,
		agents: [r.user_id],
		fields: {
			status: s.text,
			agent: r.user_id
		},
		src: {
			...s,
			user_id: r.user_id,
			current: i === 0
		}
	})));
}
var tokenize = (q) => q.toLowerCase().split(/\s+/).filter(Boolean);
function matches(rec, tokens) {
	return tokens.every((tok) => {
		const idTok = /^#(\d+)$/.exec(tok);
		if (idTok) return rec.id === Number(idTok[1]);
		if (/^\d+$/.test(tok) && rec.id === Number(tok)) return true;
		return Object.values(rec.fields).some((v) => v.toLowerCase().includes(tok));
	});
}
var escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
function markRe(tokens) {
	const words = tokens.filter((t) => !/^#\d+$/.test(t));
	return words.length ? new RegExp(`(${words.map(escapeRe).join("|")})`, "gi") : null;
}
function hl(text, re) {
	if (!re || !text) return text;
	return text.split(re).map((part, i) => i % 2 ? m$1`<mark>${part}</mark>` : part);
}
var CLIP = 220;
function excerpt(text, re) {
	if (text.length <= CLIP) return text;
	let start = 0;
	if (re) {
		re.lastIndex = 0;
		const m = re.exec(text);
		re.lastIndex = 0;
		if (m && m.index > CLIP - 60) start = Math.max(0, m.index - 70);
	}
	const end = Math.min(text.length, start + CLIP);
	return `${start > 0 ? "…" : ""}${text.slice(start, end).trimEnd()}${end < text.length ? "…" : ""}`;
}
var fmtDate = (ts) => (/* @__PURE__ */ new Date(ts * 1e3)).toLocaleString([], {
	month: "short",
	day: "numeric",
	hour: "2-digit",
	minute: "2-digit"
});
function Clipped({ label, text, re }) {
	const [open, setOpen] = d(false);
	if (!text) return null;
	const long = text.length > CLIP;
	return m$1`<div class="h-field">
    ${label && m$1`<span class="h-label">${label}</span>`}
    <span class="h-text">${hl(open || !long ? text : excerpt(text, re), re)}</span>
    ${long && m$1` <button type="button" class="h-more" onClick=${() => setOpen(!open)}>${open ? "less" : "more"}</button>`}
  </div>`;
}
function TaskTile({ rec, re, now, filterAgent }) {
	const t = rec.src;
	const f = rec.fields;
	return m$1`<article class=${`htile ${t.status}`}>
    <div class="h-who">
      ${t.assignee ? m$1`<${Avatar} name=${t.assignee} size="tiny" />
          <a class="agent-link h-agent" href=${focusHash(t.assignee)}
            title=${`Open ${t.assignee} and message it`}>${hl(t.assignee, re)}</a>
          <button type="button" class="h-only" onClick=${() => filterAgent(t.assignee)}
            title=${`Show only ${t.assignee}'s tasks`} aria-label=${`Show only ${t.assignee}'s tasks`}>⌕</button>` : m$1`<span class="h-noagent">unassigned</span>`}
      <span class=${`pill ${t.status}`}>${t.status.replace("_", " ")}</span>
    </div>
    <div class="h-title"><span class="h-id">#${t.id}</span> ${hl(f.title, re)}</div>
    <${Clipped} text=${f.description} re=${re} />
    <${AttachmentList} files=${t.attachments} />
    <${Clipped} label="how to verify" text=${f.note} re=${re} />
    <div class="h-meta">
      <span title=${fmtDate(t.created_at)}>created ${fmtDate(t.created_at)}</span>
      ${t.status === "done" ? m$1`<span title=${`last updated ${fmtDate(t.updated_at)}`}>closed ${fmtDate(t.updated_at)} · ${rel(t.updated_at, now)}</span>` : m$1`<span>updated ${rel(t.updated_at, now)}</span>`}
      ${f.team && m$1`<span>team ${hl(f.team, re)}</span>`}
      ${f.worktree && m$1`<span class="h-wt" title=${f.worktree}>${hl(f.worktree, re)}</span>`}
    </div>
  </article>`;
}
function StatusTile({ rec, re, now, filterAgent }) {
	const s = rec.src;
	return m$1`<article class="htile status-line">
    <div class="h-who">
      <${Avatar} name=${s.user_id} size="tiny" />
      <a class="agent-link h-agent" href=${focusHash(s.user_id)}
        title=${`Open ${s.user_id} and message it`}>${hl(s.user_id, re)}</a>
      <button type="button" class="h-only" onClick=${() => filterAgent(s.user_id)}
        title=${`Show only ${s.user_id}`} aria-label=${`Show only ${s.user_id}`}>⌕</button>
      <span class="pill statusline">${s.current ? "status now" : "status"}</span>
    </div>
    <div class="h-title">${hl(s.text, re)}</div>
    <div class="h-meta">
      <span title=${fmtDate(s.ts)}>${fmtDate(s.ts)} · ${rel(s.ts, now)}</span>
      <span>${SUMMARY_SOURCE[s.source] || s.source}</span>
    </div>
  </article>`;
}
var TILE = {
	task: TaskTile,
	status: StatusTile
};
function HistoryView({ state }) {
	const [s, setS] = d(() => parseHash(location.hash));
	const inputRef = A(null);
	h(() => {
		const onHash = () => {
			if (location.hash.startsWith("#/tasks")) setS(parseHash(location.hash));
		};
		const onKey = (e) => {
			if (e.key === "/" && ![
				"INPUT",
				"SELECT",
				"TEXTAREA"
			].includes(document.activeElement.tagName)) {
				e.preventDefault();
				inputRef.current?.focus();
			}
		};
		addEventListener("hashchange", onHash);
		addEventListener("keydown", onKey);
		return () => {
			removeEventListener("hashchange", onHash);
			removeEventListener("keydown", onKey);
		};
	}, []);
	const update = (patch) => {
		const next = {
			...s,
			...patch
		};
		setS(next);
		history.replaceState(null, "", historyHash(next));
	};
	const filterAgent = (a) => update({ agent: s.agent === a ? "" : a });
	const tasks = T(() => taskRecords(state.tasks, state.teams), [state.tasks, state.teams]);
	const lines = T(() => statusRecords(state.recipients), [state.recipients]);
	const tokens = tokenize(s.q);
	const re = markRe(tokens);
	const withLines = (tokens.length || s.agent) && !s.status;
	const records = withLines ? tasks.concat(lines) : tasks;
	const textHits = tokens.length ? records.filter((r) => matches(r, tokens)) : records;
	const inStatus = (r) => !s.status || r.status === s.status;
	const hasAgent = (r) => !s.agent || r.agents.includes(s.agent);
	const statusCount = {};
	for (const r of textHits) {
		if (!hasAgent(r)) continue;
		statusCount[""] = (statusCount[""] || 0) + 1;
		if (r.status) statusCount[r.status] = (statusCount[r.status] || 0) + 1;
	}
	const agentCount = /* @__PURE__ */ new Map();
	for (const r of textHits) {
		if (!inStatus(r)) continue;
		for (const a of r.agents) agentCount.set(a, (agentCount.get(a) || 0) + 1);
	}
	const agents = agentChips(agentCount, state.recipients, s.agent);
	const shown = textHits.filter((r) => inStatus(r) && hasAgent(r)).sort((a, b) => s.sort === "oldest" ? a.ts - b.ts : b.ts - a.ts);
	return m$1`<div class="history">
    <h2>task history <span class="count">· ${shown.length} of ${tasks.length} tasks${withLines ? ` + ${lines.length} status lines` : ""}</span></h2>
    <div class="h-controls">
      <input ref=${inputRef} type="text" class="h-search" value=${s.q} autofocus
        placeholder="search tasks, notes, status lines, agent, worktree, #id…  ( / to focus )"
        aria-label="Search all tasks"
        onInput=${(e) => update({ q: e.target.value })}
        onKeyDown=${(e) => {
		if (e.key === "Escape" && s.q) {
			e.stopPropagation();
			update({ q: "" });
		}
	}} />
      <div class="h-chips" role="group" aria-label="Filter by status">
        ${STATUSES.map(([v, label]) => m$1`<button type="button" key=${v}
          class=${`h-chip ${s.status === v ? "on" : ""}`} aria-pressed=${s.status === v}
          onClick=${() => update({ status: v })}>${label} <span class="n">${statusCount[v] || 0}</span></button>`)}
      </div>
      <button type="button" class="mini h-sort" onClick=${() => update({ sort: s.sort === "oldest" ? "newest" : "oldest" })}
        title="Flip the order (by creation time)">${s.sort === "oldest" ? "oldest first ↑" : "newest first ↓"}</button>
    </div>
    <div class="h-agents">
      <span class="h-label">${tokens.length ? "who worked on this" : "by agent"}</span>
      ${agents.length === 0 ? m$1`<span class="h-noagent">nobody</span>` : agents.map(([a, n]) => m$1`<button type="button" key=${a}
            class=${`h-agentchip ${s.agent === a ? "on" : ""}`} aria-pressed=${s.agent === a}
            style=${`--hue: hsl(${hue(a)} 42% 58%)`}
            title=${s.agent === a ? "Clear the agent filter" : `Show only ${a}'s tasks`}
            onClick=${() => filterAgent(a)}>${a} <span class="n">${n}</span></button>`)}
      ${(s.q || s.status || s.agent) && m$1`<button type="button" class="mini" onClick=${() => update({
		q: "",
		status: "",
		agent: ""
	})}>clear filters</button>`}
    </div>
    ${shown.length === 0 ? m$1`<div class="empty">No tasks match${s.q ? m$1` "<b>${s.q}</b>"` : ""}.</div>` : m$1`<div class="h-grid">
          ${shown.map((r) => {
		return m$1`<${TILE[r.kind]} key=${r.key} rec=${r} re=${re} now=${state.now} filterAgent=${filterAgent} />`;
	})}
        </div>`}
  </div>`;
}
//#endregion
//#region web/src/scroll-follow.js
function createBottomFollower() {
	let pinned = true;
	let lastTop = 0;
	return {
		onScroll(el) {
			const top = Math.max(0, el.scrollTop);
			if (top + el.clientHeight >= el.scrollHeight - 8) pinned = true;
			else if (top < lastTop - 1) pinned = false;
			lastTop = top;
		},
		follow(el) {
			if (pinned) el.scrollTop = el.scrollHeight;
			lastTop = Math.max(0, el.scrollTop);
		}
	};
}
//#endregion
//#region web/src/native.js
function attentionAgents(recipients) {
	return recipients.filter((r) => r.pane_alive && r.activity?.status === "needs_attention").map((r) => r.user_id).sort();
}
function attentionReporter(invoke) {
	if (!invoke) return () => {};
	let sent = null;
	return (recipients) => {
		const agents = attentionAgents(recipients);
		const key = agents.join("\n");
		if (key === sent) return;
		sent = key;
		Promise.resolve(invoke("attention", { agents })).catch(() => {
			sent = null;
		});
	};
}
//#endregion
//#region node_modules/mdurl/lib/decode.mjs
var decodeCache = {};
function getDecodeCache(exclude) {
	let cache = decodeCache[exclude];
	if (cache) return cache;
	cache = decodeCache[exclude] = [];
	for (let i = 0; i < 128; i++) {
		const ch = String.fromCharCode(i);
		cache.push(ch);
	}
	for (let i = 0; i < exclude.length; i++) {
		const ch = exclude.charCodeAt(i);
		cache[ch] = "%" + ("0" + ch.toString(16).toUpperCase()).slice(-2);
	}
	return cache;
}
function decode$1(string, exclude) {
	if (typeof exclude !== "string") exclude = decode$1.defaultChars;
	const cache = getDecodeCache(exclude);
	return string.replace(/(%[a-f0-9]{2})+/gi, function(seq) {
		let result = "";
		for (let i = 0, l = seq.length; i < l; i += 3) {
			const b1 = parseInt(seq.slice(i + 1, i + 3), 16);
			if (b1 < 128) {
				result += cache[b1];
				continue;
			}
			if ((b1 & 224) === 192 && i + 3 < l) {
				const b2 = parseInt(seq.slice(i + 4, i + 6), 16);
				if ((b2 & 192) === 128) {
					const chr = b1 << 6 & 1984 | b2 & 63;
					if (chr < 128) result += "��";
					else result += String.fromCharCode(chr);
					i += 3;
					continue;
				}
			}
			if ((b1 & 240) === 224 && i + 6 < l) {
				const b2 = parseInt(seq.slice(i + 4, i + 6), 16);
				const b3 = parseInt(seq.slice(i + 7, i + 9), 16);
				if ((b2 & 192) === 128 && (b3 & 192) === 128) {
					const chr = b1 << 12 & 61440 | b2 << 6 & 4032 | b3 & 63;
					if (chr < 2048 || chr >= 55296 && chr <= 57343) result += "���";
					else result += String.fromCharCode(chr);
					i += 6;
					continue;
				}
			}
			if ((b1 & 248) === 240 && i + 9 < l) {
				const b2 = parseInt(seq.slice(i + 4, i + 6), 16);
				const b3 = parseInt(seq.slice(i + 7, i + 9), 16);
				const b4 = parseInt(seq.slice(i + 10, i + 12), 16);
				if ((b2 & 192) === 128 && (b3 & 192) === 128 && (b4 & 192) === 128) {
					let chr = b1 << 18 & 1835008 | b2 << 12 & 258048 | b3 << 6 & 4032 | b4 & 63;
					if (chr < 65536 || chr > 1114111) result += "����";
					else {
						chr -= 65536;
						result += String.fromCharCode(55296 + (chr >> 10), 56320 + (chr & 1023));
					}
					i += 9;
					continue;
				}
			}
			result += "�";
		}
		return result;
	});
}
decode$1.defaultChars = ";/?:@&=+$,#";
decode$1.componentChars = "";
//#endregion
//#region node_modules/mdurl/lib/encode.mjs
var encodeCache = {};
function getEncodeCache(exclude) {
	let cache = encodeCache[exclude];
	if (cache) return cache;
	cache = encodeCache[exclude] = [];
	for (let i = 0; i < 128; i++) {
		const ch = String.fromCharCode(i);
		if (/^[0-9a-z]$/i.test(ch)) cache.push(ch);
		else cache.push("%" + ("0" + i.toString(16).toUpperCase()).slice(-2));
	}
	for (let i = 0; i < exclude.length; i++) cache[exclude.charCodeAt(i)] = exclude[i];
	return cache;
}
function encode$1(string, exclude, keepEscaped) {
	if (typeof exclude !== "string") {
		keepEscaped = exclude;
		exclude = encode$1.defaultChars;
	}
	if (typeof keepEscaped === "undefined") keepEscaped = true;
	const cache = getEncodeCache(exclude);
	let result = "";
	for (let i = 0, l = string.length; i < l; i++) {
		const code = string.charCodeAt(i);
		if (keepEscaped && code === 37 && i + 2 < l) {
			if (/^[0-9a-f]{2}$/i.test(string.slice(i + 1, i + 3))) {
				result += string.slice(i, i + 3);
				i += 2;
				continue;
			}
		}
		if (code < 128) {
			result += cache[code];
			continue;
		}
		if (code >= 55296 && code <= 57343) {
			if (code >= 55296 && code <= 56319 && i + 1 < l) {
				const nextCode = string.charCodeAt(i + 1);
				if (nextCode >= 56320 && nextCode <= 57343) {
					result += encodeURIComponent(string[i] + string[i + 1]);
					i++;
					continue;
				}
			}
			result += "%EF%BF%BD";
			continue;
		}
		result += encodeURIComponent(string[i]);
	}
	return result;
}
encode$1.defaultChars = ";/?:@&=+$,-_.!~*'()#";
encode$1.componentChars = "-_.!~*'()";
//#endregion
//#region node_modules/mdurl/lib/format.mjs
function format(url) {
	let result = "";
	result += url.protocol || "";
	result += url.slashes ? "//" : "";
	result += url.auth ? url.auth + "@" : "";
	if (url.hostname && url.hostname.indexOf(":") !== -1) result += "[" + url.hostname + "]";
	else result += url.hostname || "";
	result += url.port ? ":" + url.port : "";
	result += url.pathname || "";
	result += url.search || "";
	result += url.hash || "";
	return result;
}
//#endregion
//#region node_modules/mdurl/lib/parse.mjs
function Url() {
	this.protocol = null;
	this.slashes = null;
	this.auth = null;
	this.port = null;
	this.hostname = null;
	this.hash = null;
	this.search = null;
	this.pathname = null;
}
var protocolPattern = /^([a-z0-9.+-]+:)/i;
var portPattern = /:[0-9]*$/;
var simplePathPattern = /^(\/\/?(?!\/)[^\?\s]*)(\?[^\s]*)?$/;
var unwise = [
	"{",
	"}",
	"|",
	"\\",
	"^",
	"`"
].concat([
	"<",
	">",
	"\"",
	"`",
	" ",
	"\r",
	"\n",
	"	"
]);
var autoEscape = ["'"].concat(unwise);
var nonHostChars = [
	"%",
	"/",
	"?",
	";",
	"#"
].concat(autoEscape);
var hostEndingChars = [
	"/",
	"?",
	"#"
];
var hostnameMaxLen = 255;
var hostnamePartPattern = /^[+a-z0-9A-Z_-]{0,63}$/;
var hostnamePartStart = /^([+a-z0-9A-Z_-]{0,63})(.*)$/;
var hostlessProtocol = {
	javascript: true,
	"javascript:": true
};
var slashedProtocol = {
	http: true,
	https: true,
	ftp: true,
	gopher: true,
	file: true,
	"http:": true,
	"https:": true,
	"ftp:": true,
	"gopher:": true,
	"file:": true
};
function urlParse(url, slashesDenoteHost) {
	if (url && url instanceof Url) return url;
	const u = new Url();
	u.parse(url, slashesDenoteHost);
	return u;
}
Url.prototype.parse = function(url, slashesDenoteHost) {
	let lowerProto, hec, slashes;
	let rest = url;
	rest = rest.trim();
	if (!slashesDenoteHost && url.split("#").length === 1) {
		const simplePath = simplePathPattern.exec(rest);
		if (simplePath) {
			this.pathname = simplePath[1];
			if (simplePath[2]) this.search = simplePath[2];
			return this;
		}
	}
	let proto = protocolPattern.exec(rest);
	if (proto) {
		proto = proto[0];
		lowerProto = proto.toLowerCase();
		this.protocol = proto;
		rest = rest.substr(proto.length);
	}
	if (slashesDenoteHost || proto || rest.match(/^\/\/[^@\/]+@[^@\/]+/)) {
		slashes = rest.substr(0, 2) === "//";
		if (slashes && !(proto && hostlessProtocol[proto])) {
			rest = rest.substr(2);
			this.slashes = true;
		}
	}
	if (!hostlessProtocol[proto] && (slashes || proto && !slashedProtocol[proto])) {
		let hostEnd = -1;
		for (let i = 0; i < hostEndingChars.length; i++) {
			hec = rest.indexOf(hostEndingChars[i]);
			if (hec !== -1 && (hostEnd === -1 || hec < hostEnd)) hostEnd = hec;
		}
		let auth, atSign;
		if (hostEnd === -1) atSign = rest.lastIndexOf("@");
		else atSign = rest.lastIndexOf("@", hostEnd);
		if (atSign !== -1) {
			auth = rest.slice(0, atSign);
			rest = rest.slice(atSign + 1);
			this.auth = auth;
		}
		hostEnd = -1;
		for (let i = 0; i < nonHostChars.length; i++) {
			hec = rest.indexOf(nonHostChars[i]);
			if (hec !== -1 && (hostEnd === -1 || hec < hostEnd)) hostEnd = hec;
		}
		if (hostEnd === -1) hostEnd = rest.length;
		if (rest[hostEnd - 1] === ":") hostEnd--;
		const host = rest.slice(0, hostEnd);
		rest = rest.slice(hostEnd);
		this.parseHost(host);
		this.hostname = this.hostname || "";
		const ipv6Hostname = this.hostname[0] === "[" && this.hostname[this.hostname.length - 1] === "]";
		if (!ipv6Hostname) {
			const hostparts = this.hostname.split(/\./);
			for (let i = 0, l = hostparts.length; i < l; i++) {
				const part = hostparts[i];
				if (!part) continue;
				if (!part.match(hostnamePartPattern)) {
					let newpart = "";
					for (let j = 0, k = part.length; j < k; j++) if (part.charCodeAt(j) > 127) newpart += "x";
					else newpart += part[j];
					if (!newpart.match(hostnamePartPattern)) {
						const validParts = hostparts.slice(0, i);
						const notHost = hostparts.slice(i + 1);
						const bit = part.match(hostnamePartStart);
						if (bit) {
							validParts.push(bit[1]);
							notHost.unshift(bit[2]);
						}
						if (notHost.length) rest = notHost.join(".") + rest;
						this.hostname = validParts.join(".");
						break;
					}
				}
			}
		}
		if (this.hostname.length > hostnameMaxLen) this.hostname = "";
		if (ipv6Hostname) this.hostname = this.hostname.substr(1, this.hostname.length - 2);
	}
	const hash = rest.indexOf("#");
	if (hash !== -1) {
		this.hash = rest.substr(hash);
		rest = rest.slice(0, hash);
	}
	const qm = rest.indexOf("?");
	if (qm !== -1) {
		this.search = rest.substr(qm);
		rest = rest.slice(0, qm);
	}
	if (rest) this.pathname = rest;
	if (slashedProtocol[lowerProto] && this.hostname && !this.pathname) this.pathname = "";
	return this;
};
Url.prototype.parseHost = function(host) {
	let port = portPattern.exec(host);
	if (port) {
		port = port[0];
		if (port !== ":") this.port = port.substr(1);
		host = host.substr(0, host.length - port.length);
	}
	if (host) this.hostname = host;
};
//#endregion
//#region node_modules/mdurl/index.mjs
var mdurl_exports = /* @__PURE__ */ __exportAll({
	decode: () => decode$1,
	encode: () => encode$1,
	format: () => format,
	parse: () => urlParse
});
//#endregion
//#region node_modules/uc.micro/properties/Any/regex.mjs
var regex_default$5 = /[\0-\uD7FF\uE000-\uFFFF]|[\uD800-\uDBFF][\uDC00-\uDFFF]|[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?:[^\uD800-\uDBFF]|^)[\uDC00-\uDFFF]/;
//#endregion
//#region node_modules/uc.micro/categories/Cc/regex.mjs
var regex_default$4 = /[\0-\x1F\x7F-\x9F]/;
//#endregion
//#region node_modules/uc.micro/categories/Cf/regex.mjs
var regex_default$3 = /[\xAD\u0600-\u0605\u061C\u06DD\u070F\u0890\u0891\u08E2\u180E\u200B-\u200F\u202A-\u202E\u2060-\u2064\u2066-\u206F\uFEFF\uFFF9-\uFFFB]|\uD804[\uDCBD\uDCCD]|\uD80D[\uDC30-\uDC3F]|\uD82F[\uDCA0-\uDCA3]|\uD834[\uDD73-\uDD7A]|\uDB40[\uDC01\uDC20-\uDC7F]/;
//#endregion
//#region node_modules/uc.micro/categories/P/regex.mjs
var regex_default$2 = /[!-#%-\*,-\/:;\?@\[-\]_\{\}\xA1\xA7\xAB\xB6\xB7\xBB\xBF\u037E\u0387\u055A-\u055F\u0589\u058A\u05BE\u05C0\u05C3\u05C6\u05F3\u05F4\u0609\u060A\u060C\u060D\u061B\u061D-\u061F\u066A-\u066D\u06D4\u0700-\u070D\u07F7-\u07F9\u0830-\u083E\u085E\u0964\u0965\u0970\u09FD\u0A76\u0AF0\u0C77\u0C84\u0DF4\u0E4F\u0E5A\u0E5B\u0F04-\u0F12\u0F14\u0F3A-\u0F3D\u0F85\u0FD0-\u0FD4\u0FD9\u0FDA\u104A-\u104F\u10FB\u1360-\u1368\u1400\u166E\u169B\u169C\u16EB-\u16ED\u1735\u1736\u17D4-\u17D6\u17D8-\u17DA\u1800-\u180A\u1944\u1945\u1A1E\u1A1F\u1AA0-\u1AA6\u1AA8-\u1AAD\u1B5A-\u1B60\u1B7D\u1B7E\u1BFC-\u1BFF\u1C3B-\u1C3F\u1C7E\u1C7F\u1CC0-\u1CC7\u1CD3\u2010-\u2027\u2030-\u2043\u2045-\u2051\u2053-\u205E\u207D\u207E\u208D\u208E\u2308-\u230B\u2329\u232A\u2768-\u2775\u27C5\u27C6\u27E6-\u27EF\u2983-\u2998\u29D8-\u29DB\u29FC\u29FD\u2CF9-\u2CFC\u2CFE\u2CFF\u2D70\u2E00-\u2E2E\u2E30-\u2E4F\u2E52-\u2E5D\u3001-\u3003\u3008-\u3011\u3014-\u301F\u3030\u303D\u30A0\u30FB\uA4FE\uA4FF\uA60D-\uA60F\uA673\uA67E\uA6F2-\uA6F7\uA874-\uA877\uA8CE\uA8CF\uA8F8-\uA8FA\uA8FC\uA92E\uA92F\uA95F\uA9C1-\uA9CD\uA9DE\uA9DF\uAA5C-\uAA5F\uAADE\uAADF\uAAF0\uAAF1\uABEB\uFD3E\uFD3F\uFE10-\uFE19\uFE30-\uFE52\uFE54-\uFE61\uFE63\uFE68\uFE6A\uFE6B\uFF01-\uFF03\uFF05-\uFF0A\uFF0C-\uFF0F\uFF1A\uFF1B\uFF1F\uFF20\uFF3B-\uFF3D\uFF3F\uFF5B\uFF5D\uFF5F-\uFF65]|\uD800[\uDD00-\uDD02\uDF9F\uDFD0]|\uD801\uDD6F|\uD802[\uDC57\uDD1F\uDD3F\uDE50-\uDE58\uDE7F\uDEF0-\uDEF6\uDF39-\uDF3F\uDF99-\uDF9C]|\uD803[\uDEAD\uDF55-\uDF59\uDF86-\uDF89]|\uD804[\uDC47-\uDC4D\uDCBB\uDCBC\uDCBE-\uDCC1\uDD40-\uDD43\uDD74\uDD75\uDDC5-\uDDC8\uDDCD\uDDDB\uDDDD-\uDDDF\uDE38-\uDE3D\uDEA9]|\uD805[\uDC4B-\uDC4F\uDC5A\uDC5B\uDC5D\uDCC6\uDDC1-\uDDD7\uDE41-\uDE43\uDE60-\uDE6C\uDEB9\uDF3C-\uDF3E]|\uD806[\uDC3B\uDD44-\uDD46\uDDE2\uDE3F-\uDE46\uDE9A-\uDE9C\uDE9E-\uDEA2\uDF00-\uDF09]|\uD807[\uDC41-\uDC45\uDC70\uDC71\uDEF7\uDEF8\uDF43-\uDF4F\uDFFF]|\uD809[\uDC70-\uDC74]|\uD80B[\uDFF1\uDFF2]|\uD81A[\uDE6E\uDE6F\uDEF5\uDF37-\uDF3B\uDF44]|\uD81B[\uDE97-\uDE9A\uDFE2]|\uD82F\uDC9F|\uD836[\uDE87-\uDE8B]|\uD83A[\uDD5E\uDD5F]/;
//#endregion
//#region node_modules/uc.micro/categories/S/regex.mjs
var regex_default$1 = /[\$\+<->\^`\|~\xA2-\xA6\xA8\xA9\xAC\xAE-\xB1\xB4\xB8\xD7\xF7\u02C2-\u02C5\u02D2-\u02DF\u02E5-\u02EB\u02ED\u02EF-\u02FF\u0375\u0384\u0385\u03F6\u0482\u058D-\u058F\u0606-\u0608\u060B\u060E\u060F\u06DE\u06E9\u06FD\u06FE\u07F6\u07FE\u07FF\u0888\u09F2\u09F3\u09FA\u09FB\u0AF1\u0B70\u0BF3-\u0BFA\u0C7F\u0D4F\u0D79\u0E3F\u0F01-\u0F03\u0F13\u0F15-\u0F17\u0F1A-\u0F1F\u0F34\u0F36\u0F38\u0FBE-\u0FC5\u0FC7-\u0FCC\u0FCE\u0FCF\u0FD5-\u0FD8\u109E\u109F\u1390-\u1399\u166D\u17DB\u1940\u19DE-\u19FF\u1B61-\u1B6A\u1B74-\u1B7C\u1FBD\u1FBF-\u1FC1\u1FCD-\u1FCF\u1FDD-\u1FDF\u1FED-\u1FEF\u1FFD\u1FFE\u2044\u2052\u207A-\u207C\u208A-\u208C\u20A0-\u20C0\u2100\u2101\u2103-\u2106\u2108\u2109\u2114\u2116-\u2118\u211E-\u2123\u2125\u2127\u2129\u212E\u213A\u213B\u2140-\u2144\u214A-\u214D\u214F\u218A\u218B\u2190-\u2307\u230C-\u2328\u232B-\u2426\u2440-\u244A\u249C-\u24E9\u2500-\u2767\u2794-\u27C4\u27C7-\u27E5\u27F0-\u2982\u2999-\u29D7\u29DC-\u29FB\u29FE-\u2B73\u2B76-\u2B95\u2B97-\u2BFF\u2CE5-\u2CEA\u2E50\u2E51\u2E80-\u2E99\u2E9B-\u2EF3\u2F00-\u2FD5\u2FF0-\u2FFF\u3004\u3012\u3013\u3020\u3036\u3037\u303E\u303F\u309B\u309C\u3190\u3191\u3196-\u319F\u31C0-\u31E3\u31EF\u3200-\u321E\u322A-\u3247\u3250\u3260-\u327F\u328A-\u32B0\u32C0-\u33FF\u4DC0-\u4DFF\uA490-\uA4C6\uA700-\uA716\uA720\uA721\uA789\uA78A\uA828-\uA82B\uA836-\uA839\uAA77-\uAA79\uAB5B\uAB6A\uAB6B\uFB29\uFBB2-\uFBC2\uFD40-\uFD4F\uFDCF\uFDFC-\uFDFF\uFE62\uFE64-\uFE66\uFE69\uFF04\uFF0B\uFF1C-\uFF1E\uFF3E\uFF40\uFF5C\uFF5E\uFFE0-\uFFE6\uFFE8-\uFFEE\uFFFC\uFFFD]|\uD800[\uDD37-\uDD3F\uDD79-\uDD89\uDD8C-\uDD8E\uDD90-\uDD9C\uDDA0\uDDD0-\uDDFC]|\uD802[\uDC77\uDC78\uDEC8]|\uD805\uDF3F|\uD807[\uDFD5-\uDFF1]|\uD81A[\uDF3C-\uDF3F\uDF45]|\uD82F\uDC9C|\uD833[\uDF50-\uDFC3]|\uD834[\uDC00-\uDCF5\uDD00-\uDD26\uDD29-\uDD64\uDD6A-\uDD6C\uDD83\uDD84\uDD8C-\uDDA9\uDDAE-\uDDEA\uDE00-\uDE41\uDE45\uDF00-\uDF56]|\uD835[\uDEC1\uDEDB\uDEFB\uDF15\uDF35\uDF4F\uDF6F\uDF89\uDFA9\uDFC3]|\uD836[\uDC00-\uDDFF\uDE37-\uDE3A\uDE6D-\uDE74\uDE76-\uDE83\uDE85\uDE86]|\uD838[\uDD4F\uDEFF]|\uD83B[\uDCAC\uDCB0\uDD2E\uDEF0\uDEF1]|\uD83C[\uDC00-\uDC2B\uDC30-\uDC93\uDCA0-\uDCAE\uDCB1-\uDCBF\uDCC1-\uDCCF\uDCD1-\uDCF5\uDD0D-\uDDAD\uDDE6-\uDE02\uDE10-\uDE3B\uDE40-\uDE48\uDE50\uDE51\uDE60-\uDE65\uDF00-\uDFFF]|\uD83D[\uDC00-\uDED7\uDEDC-\uDEEC\uDEF0-\uDEFC\uDF00-\uDF76\uDF7B-\uDFD9\uDFE0-\uDFEB\uDFF0]|\uD83E[\uDC00-\uDC0B\uDC10-\uDC47\uDC50-\uDC59\uDC60-\uDC87\uDC90-\uDCAD\uDCB0\uDCB1\uDD00-\uDE53\uDE60-\uDE6D\uDE70-\uDE7C\uDE80-\uDE88\uDE90-\uDEBD\uDEBF-\uDEC5\uDECE-\uDEDB\uDEE0-\uDEE8\uDEF0-\uDEF8\uDF00-\uDF92\uDF94-\uDFCA]/;
//#endregion
//#region node_modules/uc.micro/categories/Z/regex.mjs
var regex_default = /[ \xA0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]/;
//#endregion
//#region node_modules/uc.micro/index.mjs
var uc_micro_exports = /* @__PURE__ */ __exportAll({
	Any: () => regex_default$5,
	Cc: () => regex_default$4,
	Cf: () => regex_default$3,
	P: () => regex_default$2,
	S: () => regex_default$1,
	Z: () => regex_default
});
//#endregion
//#region node_modules/entities/lib/esm/generated/decode-data-html.js
var decode_data_html_default = new Uint16Array("ᵁ<Õıʊҝջאٵ۞ޢߖࠏ੊ઑඡ๭༉༦჊ረዡᐕᒝᓃᓟᔥ\0\0\0\0\0\0ᕫᛍᦍᰒᷝ὾⁠↰⊍⏀⏻⑂⠤⤒ⴈ⹈⿎〖㊺㘹㞬㣾㨨㩱㫠㬮ࠀEMabcfglmnoprstu\\bfms¦³¹ÈÏlig耻Æ䃆P耻&䀦cute耻Á䃁reve;䄂Āiyx}rc耻Â䃂;䐐r;쀀𝔄rave耻À䃀pha;䎑acr;䄀d;橓Āgp¡on;䄄f;쀀𝔸plyFunction;恡ing耻Å䃅Ācs¾Ãr;쀀𝒜ign;扔ilde耻Ã䃃ml耻Ä䃄ЀaceforsuåûþėĜĢħĪĀcrêòkslash;或Ŷöø;櫧ed;挆y;䐑ƀcrtąċĔause;戵noullis;愬a;䎒r;쀀𝔅pf;쀀𝔹eve;䋘còēmpeq;扎܀HOacdefhilorsuōőŖƀƞƢƵƷƺǜȕɳɸɾcy;䐧PY耻©䂩ƀcpyŝŢźute;䄆Ā;iŧŨ拒talDifferentialD;慅leys;愭ȀaeioƉƎƔƘron;䄌dil耻Ç䃇rc;䄈nint;戰ot;䄊ĀdnƧƭilla;䂸terDot;䂷òſi;䎧rcleȀDMPTǇǋǑǖot;抙inus;抖lus;投imes;抗oĀcsǢǸkwiseContourIntegral;戲eCurlyĀDQȃȏoubleQuote;思uote;怙ȀlnpuȞȨɇɕonĀ;eȥȦ户;橴ƀgitȯȶȺruent;扡nt;戯ourIntegral;戮ĀfrɌɎ;愂oduct;成nterClockwiseContourIntegral;戳oss;樯cr;쀀𝒞pĀ;Cʄʅ拓ap;才րDJSZacefiosʠʬʰʴʸˋ˗ˡ˦̳ҍĀ;oŹʥtrahd;椑cy;䐂cy;䐅cy;䐏ƀgrsʿ˄ˇger;怡r;憡hv;櫤Āayː˕ron;䄎;䐔lĀ;t˝˞戇a;䎔r;쀀𝔇Āaf˫̧Ācm˰̢riticalȀADGT̖̜̀̆cute;䂴oŴ̋̍;䋙bleAcute;䋝rave;䁠ilde;䋜ond;拄ferentialD;慆Ѱ̽\0\0\0͔͂\0Ѕf;쀀𝔻ƀ;DE͈͉͍䂨ot;惜qual;扐blèCDLRUVͣͲ΂ϏϢϸontourIntegraìȹoɴ͹\0\0ͻ»͉nArrow;懓Āeo·ΤftƀARTΐΖΡrrow;懐ightArrow;懔eåˊngĀLRΫτeftĀARγιrrow;柸ightArrow;柺ightArrow;柹ightĀATϘϞrrow;懒ee;抨pɁϩ\0\0ϯrrow;懑ownArrow;懕erticalBar;戥ǹABLRTaВЪаўѿͼrrowƀ;BUНОТ憓ar;椓pArrow;懵reve;䌑eft˒к\0ц\0ѐightVector;楐eeVector;楞ectorĀ;Bљњ憽ar;楖ightǔѧ\0ѱeeVector;楟ectorĀ;BѺѻ懁ar;楗eeĀ;A҆҇护rrow;憧ĀctҒҗr;쀀𝒟rok;䄐ࠀNTacdfglmopqstuxҽӀӄӋӞӢӧӮӵԡԯԶՒ՝ՠեG;䅊H耻Ð䃐cute耻É䃉ƀaiyӒӗӜron;䄚rc耻Ê䃊;䐭ot;䄖r;쀀𝔈rave耻È䃈ement;戈ĀapӺӾcr;䄒tyɓԆ\0\0ԒmallSquare;旻erySmallSquare;斫ĀgpԦԪon;䄘f;쀀𝔼silon;䎕uĀaiԼՉlĀ;TՂՃ橵ilde;扂librium;懌Āci՗՚r;愰m;橳a;䎗ml耻Ë䃋Āipժկsts;戃onentialE;慇ʀcfiosօֈ֍ֲ׌y;䐤r;쀀𝔉lledɓ֗\0\0֣mallSquare;旼erySmallSquare;斪Ͱֺ\0ֿ\0\0ׄf;쀀𝔽All;戀riertrf;愱cò׋؀JTabcdfgorstר׬ׯ׺؀ؒؖ؛؝أ٬ٲcy;䐃耻>䀾mmaĀ;d׷׸䎓;䏜reve;䄞ƀeiy؇،ؐdil;䄢rc;䄜;䐓ot;䄠r;쀀𝔊;拙pf;쀀𝔾eater̀EFGLSTصلَٖٛ٦qualĀ;Lؾؿ扥ess;招ullEqual;执reater;檢ess;扷lantEqual;橾ilde;扳cr;쀀𝒢;扫ЀAacfiosuڅڋږڛڞڪھۊRDcy;䐪Āctڐڔek;䋇;䁞irc;䄤r;愌lbertSpace;愋ǰگ\0ڲf;愍izontalLine;攀Āctۃۅòکrok;䄦mpńېۘownHumðįqual;扏܀EJOacdfgmnostuۺ۾܃܇܎ܚܞܡܨ݄ݸދޏޕcy;䐕lig;䄲cy;䐁cute耻Í䃍Āiyܓܘrc耻Î䃎;䐘ot;䄰r;愑rave耻Ì䃌ƀ;apܠܯܿĀcgܴܷr;䄪inaryI;慈lieóϝǴ݉\0ݢĀ;eݍݎ戬Āgrݓݘral;戫section;拂isibleĀCTݬݲomma;恣imes;恢ƀgptݿރވon;䄮f;쀀𝕀a;䎙cr;愐ilde;䄨ǫޚ\0ޞcy;䐆l耻Ï䃏ʀcfosuެ޷޼߂ߐĀiyޱ޵rc;䄴;䐙r;쀀𝔍pf;쀀𝕁ǣ߇\0ߌr;쀀𝒥rcy;䐈kcy;䐄΀HJacfosߤߨ߽߬߱ࠂࠈcy;䐥cy;䐌ppa;䎚Āey߶߻dil;䄶;䐚r;쀀𝔎pf;쀀𝕂cr;쀀𝒦րJTaceflmostࠥࠩࠬࡐࡣ঳সে্਷ੇcy;䐉耻<䀼ʀcmnpr࠷࠼ࡁࡄࡍute;䄹bda;䎛g;柪lacetrf;愒r;憞ƀaeyࡗ࡜ࡡron;䄽dil;䄻;䐛Āfsࡨ॰tԀACDFRTUVarࡾࢩࢱࣦ࣠ࣼयज़ΐ४Ānrࢃ࢏gleBracket;柨rowƀ;BR࢙࢚࢞憐ar;懤ightArrow;懆eiling;挈oǵࢷ\0ࣃbleBracket;柦nǔࣈ\0࣒eeVector;楡ectorĀ;Bࣛࣜ懃ar;楙loor;挊ightĀAV࣯ࣵrrow;憔ector;楎Āerँगeƀ;AVउऊऐ抣rrow;憤ector;楚iangleƀ;BEतथऩ抲ar;槏qual;抴pƀDTVषूौownVector;楑eeVector;楠ectorĀ;Bॖॗ憿ar;楘ectorĀ;B॥०憼ar;楒ightáΜs̀EFGLSTॾঋকঝঢভqualGreater;拚ullEqual;扦reater;扶ess;檡lantEqual;橽ilde;扲r;쀀𝔏Ā;eঽা拘ftarrow;懚idot;䄿ƀnpw৔ਖਛgȀLRlr৞৷ਂਐeftĀAR০৬rrow;柵ightArrow;柷ightArrow;柶eftĀarγਊightáοightáϊf;쀀𝕃erĀLRਢਬeftArrow;憙ightArrow;憘ƀchtਾੀੂòࡌ;憰rok;䅁;扪Ѐacefiosuਗ਼੝੠੷੼અઋ઎p;椅y;䐜Ādl੥੯iumSpace;恟lintrf;愳r;쀀𝔐nusPlus;戓pf;쀀𝕄cò੶;䎜ҀJacefostuણધભીଔଙඑ඗ඞcy;䐊cute;䅃ƀaey઴હાron;䅇dil;䅅;䐝ƀgswે૰଎ativeƀMTV૓૟૨ediumSpace;怋hiĀcn૦૘ë૙eryThiî૙tedĀGL૸ଆreaterGreateòٳessLesóੈLine;䀊r;쀀𝔑ȀBnptଢନଷ଺reak;恠BreakingSpace;䂠f;愕ڀ;CDEGHLNPRSTV୕ୖ୪୼஡௫ఄ౞಄ದ೘ൡඅ櫬Āou୛୤ngruent;扢pCap;扭oubleVerticalBar;戦ƀlqxஃஊ஛ement;戉ualĀ;Tஒஓ扠ilde;쀀≂̸ists;戄reater΀;EFGLSTஶஷ஽௉௓௘௥扯qual;扱ullEqual;쀀≧̸reater;쀀≫̸ess;批lantEqual;쀀⩾̸ilde;扵umpń௲௽ownHump;쀀≎̸qual;쀀≏̸eĀfsఊధtTriangleƀ;BEచఛడ拪ar;쀀⧏̸qual;括s̀;EGLSTవశ఼ౄోౘ扮qual;扰reater;扸ess;쀀≪̸lantEqual;쀀⩽̸ilde;扴estedĀGL౨౹reaterGreater;쀀⪢̸essLess;쀀⪡̸recedesƀ;ESಒಓಛ技qual;쀀⪯̸lantEqual;拠ĀeiಫಹverseElement;戌ghtTriangleƀ;BEೋೌ೒拫ar;쀀⧐̸qual;拭ĀquೝഌuareSuĀbp೨೹setĀ;E೰ೳ쀀⊏̸qual;拢ersetĀ;Eഃആ쀀⊐̸qual;拣ƀbcpഓതൎsetĀ;Eഛഞ쀀⊂⃒qual;抈ceedsȀ;ESTലള഻െ抁qual;쀀⪰̸lantEqual;拡ilde;쀀≿̸ersetĀ;E൘൛쀀⊃⃒qual;抉ildeȀ;EFT൮൯൵ൿ扁qual;扄ullEqual;扇ilde;扉erticalBar;戤cr;쀀𝒩ilde耻Ñ䃑;䎝܀Eacdfgmoprstuvලෂ෉෕ෛ෠෧෼ขภยา฿ไlig;䅒cute耻Ó䃓Āiy෎ීrc耻Ô䃔;䐞blac;䅐r;쀀𝔒rave耻Ò䃒ƀaei෮ෲ෶cr;䅌ga;䎩cron;䎟pf;쀀𝕆enCurlyĀDQฎบoubleQuote;怜uote;怘;橔Āclวฬr;쀀𝒪ash耻Ø䃘iŬื฼de耻Õ䃕es;樷ml耻Ö䃖erĀBP๋๠Āar๐๓r;怾acĀek๚๜;揞et;掴arenthesis;揜Ҁacfhilors๿ງຊຏຒດຝະ໼rtialD;戂y;䐟r;쀀𝔓i;䎦;䎠usMinus;䂱Āipຢອncareplanåڝf;愙Ȁ;eio຺ູ໠໤檻cedesȀ;EST່້໏໚扺qual;檯lantEqual;扼ilde;找me;怳Ādp໩໮uct;戏ortionĀ;aȥ໹l;戝Āci༁༆r;쀀𝒫;䎨ȀUfos༑༖༛༟OT耻\"䀢r;쀀𝔔pf;愚cr;쀀𝒬؀BEacefhiorsu༾གྷཇའཱིྦྷྪྭ႖ႩႴႾarr;椐G耻®䂮ƀcnrཎནབute;䅔g;柫rĀ;tཛྷཝ憠l;椖ƀaeyཧཬཱron;䅘dil;䅖;䐠Ā;vླྀཹ愜erseĀEUྂྙĀlq྇ྎement;戋uilibrium;懋pEquilibrium;楯r»ཹo;䎡ghtЀACDFTUVa࿁࿫࿳ဢဨၛႇϘĀnr࿆࿒gleBracket;柩rowƀ;BL࿜࿝࿡憒ar;懥eftArrow;懄eiling;按oǵ࿹\0စbleBracket;柧nǔည\0နeeVector;楝ectorĀ;Bဝသ懂ar;楕loor;挋Āerိ၃eƀ;AVဵံြ抢rrow;憦ector;楛iangleƀ;BEၐၑၕ抳ar;槐qual;抵pƀDTVၣၮၸownVector;楏eeVector;楜ectorĀ;Bႂႃ憾ar;楔ectorĀ;B႑႒懀ar;楓Āpuႛ႞f;愝ndImplies;楰ightarrow;懛ĀchႹႼr;愛;憱leDelayed;槴ڀHOacfhimoqstuფჱჷჽᄙᄞᅑᅖᅡᅧᆵᆻᆿĀCcჩხHcy;䐩y;䐨FTcy;䐬cute;䅚ʀ;aeiyᄈᄉᄎᄓᄗ檼ron;䅠dil;䅞rc;䅜;䐡r;쀀𝔖ortȀDLRUᄪᄴᄾᅉownArrow»ОeftArrow»࢚ightArrow»࿝pArrow;憑gma;䎣allCircle;战pf;쀀𝕊ɲᅭ\0\0ᅰt;戚areȀ;ISUᅻᅼᆉᆯ斡ntersection;抓uĀbpᆏᆞsetĀ;Eᆗᆘ抏qual;抑ersetĀ;Eᆨᆩ抐qual;抒nion;抔cr;쀀𝒮ar;拆ȀbcmpᇈᇛሉላĀ;sᇍᇎ拐etĀ;Eᇍᇕqual;抆ĀchᇠህeedsȀ;ESTᇭᇮᇴᇿ扻qual;檰lantEqual;扽ilde;承Tháྌ;我ƀ;esሒሓሣ拑rsetĀ;Eሜም抃qual;抇et»ሓրHRSacfhiorsሾቄ቉ቕ቞ቱቶኟዂወዑORN耻Þ䃞ADE;愢ĀHc቎ቒcy;䐋y;䐦Ābuቚቜ;䀉;䎤ƀaeyብቪቯron;䅤dil;䅢;䐢r;쀀𝔗Āeiቻ኉ǲኀ\0ኇefore;戴a;䎘Ācn኎ኘkSpace;쀀  Space;怉ldeȀ;EFTካኬኲኼ戼qual;扃ullEqual;扅ilde;扈pf;쀀𝕋ipleDot;惛Āctዖዛr;쀀𝒯rok;䅦ૡዷጎጚጦ\0ጬጱ\0\0\0\0\0ጸጽ፷ᎅ\0᏿ᐄᐊᐐĀcrዻጁute耻Ú䃚rĀ;oጇገ憟cir;楉rǣጓ\0጖y;䐎ve;䅬Āiyጞጣrc耻Û䃛;䐣blac;䅰r;쀀𝔘rave耻Ù䃙acr;䅪Ādiፁ፩erĀBPፈ፝Āarፍፐr;䁟acĀekፗፙ;揟et;掵arenthesis;揝onĀ;P፰፱拃lus;抎Āgp፻፿on;䅲f;쀀𝕌ЀADETadps᎕ᎮᎸᏄϨᏒᏗᏳrrowƀ;BDᅐᎠᎤar;椒ownArrow;懅ownArrow;憕quilibrium;楮eeĀ;AᏋᏌ报rrow;憥ownáϳerĀLRᏞᏨeftArrow;憖ightArrow;憗iĀ;lᏹᏺ䏒on;䎥ing;䅮cr;쀀𝒰ilde;䅨ml耻Ü䃜ҀDbcdefosvᐧᐬᐰᐳᐾᒅᒊᒐᒖash;披ar;櫫y;䐒ashĀ;lᐻᐼ抩;櫦Āerᑃᑅ;拁ƀbtyᑌᑐᑺar;怖Ā;iᑏᑕcalȀBLSTᑡᑥᑪᑴar;戣ine;䁼eparator;杘ilde;所ThinSpace;怊r;쀀𝔙pf;쀀𝕍cr;쀀𝒱dash;抪ʀcefosᒧᒬᒱᒶᒼirc;䅴dge;拀r;쀀𝔚pf;쀀𝕎cr;쀀𝒲Ȁfiosᓋᓐᓒᓘr;쀀𝔛;䎞pf;쀀𝕏cr;쀀𝒳ҀAIUacfosuᓱᓵᓹᓽᔄᔏᔔᔚᔠcy;䐯cy;䐇cy;䐮cute耻Ý䃝Āiyᔉᔍrc;䅶;䐫r;쀀𝔜pf;쀀𝕐cr;쀀𝒴ml;䅸ЀHacdefosᔵᔹᔿᕋᕏᕝᕠᕤcy;䐖cute;䅹Āayᕄᕉron;䅽;䐗ot;䅻ǲᕔ\0ᕛoWidtè૙a;䎖r;愨pf;愤cr;쀀𝒵௡ᖃᖊᖐ\0ᖰᖶᖿ\0\0\0\0ᗆᗛᗫᙟ᙭\0ᚕ᚛ᚲᚹ\0ᚾcute耻á䃡reve;䄃̀;Ediuyᖜᖝᖡᖣᖨᖭ戾;쀀∾̳;房rc耻â䃢te肻´̆;䐰lig耻æ䃦Ā;r²ᖺ;쀀𝔞rave耻à䃠ĀepᗊᗖĀfpᗏᗔsym;愵èᗓha;䎱ĀapᗟcĀclᗤᗧr;䄁g;樿ɤᗰ\0\0ᘊʀ;adsvᗺᗻᗿᘁᘇ戧nd;橕;橜lope;橘;橚΀;elmrszᘘᘙᘛᘞᘿᙏᙙ戠;榤e»ᘙsdĀ;aᘥᘦ戡ѡᘰᘲᘴᘶᘸᘺᘼᘾ;榨;榩;榪;榫;榬;榭;榮;榯tĀ;vᙅᙆ戟bĀ;dᙌᙍ抾;榝Āptᙔᙗh;戢»¹arr;捼Āgpᙣᙧon;䄅f;쀀𝕒΀;Eaeiop዁ᙻᙽᚂᚄᚇᚊ;橰cir;橯;扊d;手s;䀧roxĀ;e዁ᚒñᚃing耻å䃥ƀctyᚡᚦᚨr;쀀𝒶;䀪mpĀ;e዁ᚯñʈilde耻ã䃣ml耻ä䃤Āciᛂᛈoninôɲnt;樑ࠀNabcdefiklnoprsu᛭ᛱᜰ᜼ᝃᝈ᝸᝽០៦ᠹᡐᜍ᤽᥈ᥰot;櫭Ācrᛶ᜞kȀcepsᜀᜅᜍᜓong;扌psilon;䏶rime;怵imĀ;e᜚᜛戽q;拍Ŷᜢᜦee;抽edĀ;gᜬᜭ挅e»ᜭrkĀ;t፜᜷brk;掶Āoyᜁᝁ;䐱quo;怞ʀcmprtᝓ᝛ᝡᝤᝨausĀ;eĊĉptyv;榰séᜌnoõēƀahwᝯ᝱ᝳ;䎲;愶een;扬r;쀀𝔟g΀costuvwឍឝឳេ៕៛៞ƀaiuបពរðݠrc;旯p»፱ƀdptឤឨឭot;樀lus;樁imes;樂ɱឹ\0\0ើcup;樆ar;昅riangleĀdu៍្own;施p;斳plus;樄eåᑄåᒭarow;植ƀako៭ᠦᠵĀcn៲ᠣkƀlst៺֫᠂ozenge;槫riangleȀ;dlr᠒᠓᠘᠝斴own;斾eft;旂ight;斸k;搣Ʊᠫ\0ᠳƲᠯ\0ᠱ;斒;斑4;斓ck;斈ĀeoᠾᡍĀ;qᡃᡆ쀀=⃥uiv;쀀≡⃥t;挐Ȁptwxᡙᡞᡧᡬf;쀀𝕓Ā;tᏋᡣom»Ꮜtie;拈؀DHUVbdhmptuvᢅᢖᢪᢻᣗᣛᣬ᣿ᤅᤊᤐᤡȀLRlrᢎᢐᢒᢔ;敗;敔;敖;敓ʀ;DUduᢡᢢᢤᢦᢨ敐;敦;敩;敤;敧ȀLRlrᢳᢵᢷᢹ;敝;敚;敜;教΀;HLRhlrᣊᣋᣍᣏᣑᣓᣕ救;敬;散;敠;敫;敢;敟ox;槉ȀLRlrᣤᣦᣨᣪ;敕;敒;攐;攌ʀ;DUduڽ᣷᣹᣻᣽;敥;敨;攬;攴inus;抟lus;択imes;抠ȀLRlrᤙᤛᤝ᤟;敛;敘;攘;攔΀;HLRhlrᤰᤱᤳᤵᤷ᤻᤹攂;敪;敡;敞;攼;攤;攜Āevģ᥂bar耻¦䂦Ȁceioᥑᥖᥚᥠr;쀀𝒷mi;恏mĀ;e᜚᜜lƀ;bhᥨᥩᥫ䁜;槅sub;柈Ŭᥴ᥾lĀ;e᥹᥺怢t»᥺pƀ;Eeįᦅᦇ;檮Ā;qۜۛೡᦧ\0᧨ᨑᨕᨲ\0ᨷᩐ\0\0᪴\0\0᫁\0\0ᬡᬮ᭍᭒\0᯽\0ᰌƀcpr᦭ᦲ᧝ute;䄇̀;abcdsᦿᧀᧄ᧊᧕᧙戩nd;橄rcup;橉Āau᧏᧒p;橋p;橇ot;橀;쀀∩︀Āeo᧢᧥t;恁îړȀaeiu᧰᧻ᨁᨅǰ᧵\0᧸s;橍on;䄍dil耻ç䃧rc;䄉psĀ;sᨌᨍ橌m;橐ot;䄋ƀdmnᨛᨠᨦil肻¸ƭptyv;榲t脀¢;eᨭᨮ䂢räƲr;쀀𝔠ƀceiᨽᩀᩍy;䑇ckĀ;mᩇᩈ朓ark»ᩈ;䏇r΀;Ecefms᩟᩠ᩢᩫ᪤᪪᪮旋;槃ƀ;elᩩᩪᩭ䋆q;扗eɡᩴ\0\0᪈rrowĀlr᩼᪁eft;憺ight;憻ʀRSacd᪒᪔᪖᪚᪟»ཇ;擈st;抛irc;抚ash;抝nint;樐id;櫯cir;槂ubsĀ;u᪻᪼晣it»᪼ˬ᫇᫔᫺\0ᬊonĀ;eᫍᫎ䀺Ā;qÇÆɭ᫙\0\0᫢aĀ;t᫞᫟䀬;䁀ƀ;fl᫨᫩᫫戁îᅠeĀmx᫱᫶ent»᫩eóɍǧ᫾\0ᬇĀ;dኻᬂot;橭nôɆƀfryᬐᬔᬗ;쀀𝕔oäɔ脀©;sŕᬝr;愗Āaoᬥᬩrr;憵ss;朗Ācuᬲᬷr;쀀𝒸Ābpᬼ᭄Ā;eᭁᭂ櫏;櫑Ā;eᭉᭊ櫐;櫒dot;拯΀delprvw᭠᭬᭷ᮂᮬᯔ᯹arrĀlr᭨᭪;椸;椵ɰ᭲\0\0᭵r;拞c;拟arrĀ;p᭿ᮀ憶;椽̀;bcdosᮏᮐᮖᮡᮥᮨ截rcap;橈Āauᮛᮞp;橆p;橊ot;抍r;橅;쀀∪︀Ȁalrv᮵ᮿᯞᯣrrĀ;mᮼᮽ憷;椼yƀevwᯇᯔᯘqɰᯎ\0\0ᯒreã᭳uã᭵ee;拎edge;拏en耻¤䂤earrowĀlrᯮ᯳eft»ᮀight»ᮽeäᯝĀciᰁᰇoninôǷnt;戱lcty;挭ঀAHabcdefhijlorstuwz᰸᰻᰿ᱝᱩᱵᲊᲞᲬᲷ᳻᳿ᴍᵻᶑᶫᶻ᷆᷍rò΁ar;楥Ȁglrs᱈ᱍ᱒᱔ger;怠eth;愸òᄳhĀ;vᱚᱛ怐»ऊūᱡᱧarow;椏aã̕Āayᱮᱳron;䄏;䐴ƀ;ao̲ᱼᲄĀgrʿᲁr;懊tseq;橷ƀglmᲑᲔᲘ耻°䂰ta;䎴ptyv;榱ĀirᲣᲨsht;楿;쀀𝔡arĀlrᲳᲵ»ࣜ»သʀaegsv᳂͸᳖᳜᳠mƀ;oș᳊᳔ndĀ;ș᳑uit;晦amma;䏝in;拲ƀ;io᳧᳨᳸䃷de脀÷;o᳧ᳰntimes;拇nø᳷cy;䑒cɯᴆ\0\0ᴊrn;挞op;挍ʀlptuwᴘᴝᴢᵉᵕlar;䀤f;쀀𝕕ʀ;emps̋ᴭᴷᴽᵂqĀ;d͒ᴳot;扑inus;戸lus;戔quare;抡blebarwedgåúnƀadhᄮᵝᵧownarrowóᲃarpoonĀlrᵲᵶefôᲴighôᲶŢᵿᶅkaro÷གɯᶊ\0\0ᶎrn;挟op;挌ƀcotᶘᶣᶦĀryᶝᶡ;쀀𝒹;䑕l;槶rok;䄑Ādrᶰᶴot;拱iĀ;fᶺ᠖斿Āah᷀᷃ròЩaòྦangle;榦Āci᷒ᷕy;䑟grarr;柿ऀDacdefglmnopqrstuxḁḉḙḸոḼṉṡṾấắẽỡἪἷὄ὎὚ĀDoḆᴴoôᲉĀcsḎḔute耻é䃩ter;橮ȀaioyḢḧḱḶron;䄛rĀ;cḭḮ扖耻ê䃪lon;払;䑍ot;䄗ĀDrṁṅot;扒;쀀𝔢ƀ;rsṐṑṗ檚ave耻è䃨Ā;dṜṝ檖ot;檘Ȁ;ilsṪṫṲṴ檙nters;揧;愓Ā;dṹṺ檕ot;檗ƀapsẅẉẗcr;䄓tyƀ;svẒẓẕ戅et»ẓpĀ1;ẝẤĳạả;怄;怅怃ĀgsẪẬ;䅋p;怂ĀgpẴẸon;䄙f;쀀𝕖ƀalsỄỎỒrĀ;sỊị拕l;槣us;橱iƀ;lvỚớở䎵on»ớ;䏵ȀcsuvỪỳἋἣĀioữḱrc»Ḯɩỹ\0\0ỻíՈantĀglἂἆtr»ṝess»Ṻƀaeiἒ἖Ἒls;䀽st;扟vĀ;DȵἠD;橸parsl;槥ĀDaἯἳot;打rr;楱ƀcdiἾὁỸr;愯oô͒ĀahὉὋ;䎷耻ð䃰Āmrὓὗl耻ë䃫o;悬ƀcipὡὤὧl;䀡sôծĀeoὬὴctatioîՙnentialåչৡᾒ\0ᾞ\0ᾡᾧ\0\0ῆῌ\0ΐ\0ῦῪ \0 ⁚llingdotseñṄy;䑄male;晀ƀilrᾭᾳ῁lig;耀ﬃɩᾹ\0\0᾽g;耀ﬀig;耀ﬄ;쀀𝔣lig;耀ﬁlig;쀀fjƀaltῙ῜ῡt;晭ig;耀ﬂns;斱of;䆒ǰ΅\0ῳf;쀀𝕗ĀakֿῷĀ;vῼ´拔;櫙artint;樍Āao‌⁕Ācs‑⁒α‚‰‸⁅⁈\0⁐β•‥‧‪‬\0‮耻½䂽;慓耻¼䂼;慕;慙;慛Ƴ‴\0‶;慔;慖ʴ‾⁁\0\0⁃耻¾䂾;慗;慜5;慘ƶ⁌\0⁎;慚;慝8;慞l;恄wn;挢cr;쀀𝒻ࢀEabcdefgijlnorstv₂₉₟₥₰₴⃰⃵⃺⃿℃ℒℸ̗ℾ⅒↞Ā;lٍ₇;檌ƀcmpₐₕ₝ute;䇵maĀ;dₜ᳚䎳;檆reve;䄟Āiy₪₮rc;䄝;䐳ot;䄡Ȁ;lqsؾق₽⃉ƀ;qsؾٌ⃄lanô٥Ȁ;cdl٥⃒⃥⃕c;檩otĀ;o⃜⃝檀Ā;l⃢⃣檂;檄Ā;e⃪⃭쀀⋛︀s;檔r;쀀𝔤Ā;gٳ؛mel;愷cy;䑓Ȁ;Eajٚℌℎℐ;檒;檥;檤ȀEaesℛℝ℩ℴ;扩pĀ;p℣ℤ檊rox»ℤĀ;q℮ℯ檈Ā;q℮ℛim;拧pf;쀀𝕘Āci⅃ⅆr;愊mƀ;el٫ⅎ⅐;檎;檐茀>;cdlqr׮ⅠⅪⅮⅳⅹĀciⅥⅧ;檧r;橺ot;拗Par;榕uest;橼ʀadelsↄⅪ←ٖ↛ǰ↉\0↎proø₞r;楸qĀlqؿ↖lesó₈ií٫Āen↣↭rtneqq;쀀≩︀Å↪ԀAabcefkosy⇄⇇⇱⇵⇺∘∝∯≨≽ròΠȀilmr⇐⇔⇗⇛rsðᒄf»․ilôکĀdr⇠⇤cy;䑊ƀ;cwࣴ⇫⇯ir;楈;憭ar;意irc;䄥ƀalr∁∎∓rtsĀ;u∉∊晥it»∊lip;怦con;抹r;쀀𝔥sĀew∣∩arow;椥arow;椦ʀamopr∺∾≃≞≣rr;懿tht;戻kĀlr≉≓eftarrow;憩ightarrow;憪f;쀀𝕙bar;怕ƀclt≯≴≸r;쀀𝒽asè⇴rok;䄧Ābp⊂⊇ull;恃hen»ᱛૡ⊣\0⊪\0⊸⋅⋎\0⋕⋳\0\0⋸⌢⍧⍢⍿\0⎆⎪⎴cute耻í䃭ƀ;iyݱ⊰⊵rc耻î䃮;䐸Ācx⊼⊿y;䐵cl耻¡䂡ĀfrΟ⋉;쀀𝔦rave耻ì䃬Ȁ;inoܾ⋝⋩⋮Āin⋢⋦nt;樌t;戭fin;槜ta;愩lig;䄳ƀaop⋾⌚⌝ƀcgt⌅⌈⌗r;䄫ƀelpܟ⌏⌓inåގarôܠh;䄱f;抷ed;䆵ʀ;cfotӴ⌬⌱⌽⍁are;愅inĀ;t⌸⌹戞ie;槝doô⌙ʀ;celpݗ⍌⍐⍛⍡al;抺Āgr⍕⍙eróᕣã⍍arhk;樗rod;樼Ȁcgpt⍯⍲⍶⍻y;䑑on;䄯f;쀀𝕚a;䎹uest耻¿䂿Āci⎊⎏r;쀀𝒾nʀ;EdsvӴ⎛⎝⎡ӳ;拹ot;拵Ā;v⎦⎧拴;拳Ā;iݷ⎮lde;䄩ǫ⎸\0⎼cy;䑖l耻ï䃯̀cfmosu⏌⏗⏜⏡⏧⏵Āiy⏑⏕rc;䄵;䐹r;쀀𝔧ath;䈷pf;쀀𝕛ǣ⏬\0⏱r;쀀𝒿rcy;䑘kcy;䑔Ѐacfghjos␋␖␢␧␭␱␵␻ppaĀ;v␓␔䎺;䏰Āey␛␠dil;䄷;䐺r;쀀𝔨reen;䄸cy;䑅cy;䑜pf;쀀𝕜cr;쀀𝓀஀ABEHabcdefghjlmnoprstuv⑰⒁⒆⒍⒑┎┽╚▀♎♞♥♹♽⚚⚲⛘❝❨➋⟀⠁⠒ƀart⑷⑺⑼rò৆òΕail;椛arr;椎Ā;gঔ⒋;檋ar;楢ॣ⒥\0⒪\0⒱\0\0\0\0\0⒵Ⓔ\0ⓆⓈⓍ\0⓹ute;䄺mptyv;榴raîࡌbda;䎻gƀ;dlࢎⓁⓃ;榑åࢎ;檅uo耻«䂫rЀ;bfhlpst࢙ⓞⓦⓩ⓫⓮⓱⓵Ā;f࢝ⓣs;椟s;椝ë≒p;憫l;椹im;楳l;憢ƀ;ae⓿─┄檫il;椙Ā;s┉┊檭;쀀⪭︀ƀabr┕┙┝rr;椌rk;杲Āak┢┬cĀek┨┪;䁻;䁛Āes┱┳;榋lĀdu┹┻;榏;榍Ȁaeuy╆╋╖╘ron;䄾Ādi═╔il;䄼ìࢰâ┩;䐻Ȁcqrs╣╦╭╽a;椶uoĀ;rนᝆĀdu╲╷har;楧shar;楋h;憲ʀ;fgqs▋▌উ◳◿扤tʀahlrt▘▤▷◂◨rrowĀ;t࢙□aé⓶arpoonĀdu▯▴own»њp»०eftarrows;懇ightƀahs◍◖◞rrowĀ;sࣴࢧarpoonó྘quigarro÷⇰hreetimes;拋ƀ;qs▋ও◺lanôবʀ;cdgsব☊☍☝☨c;檨otĀ;o☔☕橿Ā;r☚☛檁;檃Ā;e☢☥쀀⋚︀s;檓ʀadegs☳☹☽♉♋pproøⓆot;拖qĀgq♃♅ôউgtò⒌ôছiíলƀilr♕࣡♚sht;楼;쀀𝔩Ā;Eজ♣;檑š♩♶rĀdu▲♮Ā;l॥♳;楪lk;斄cy;䑙ʀ;achtੈ⚈⚋⚑⚖rò◁orneòᴈard;楫ri;旺Āio⚟⚤dot;䅀ustĀ;a⚬⚭掰che»⚭ȀEaes⚻⚽⛉⛔;扨pĀ;p⛃⛄檉rox»⛄Ā;q⛎⛏檇Ā;q⛎⚻im;拦Ѐabnoptwz⛩⛴⛷✚✯❁❇❐Ānr⛮⛱g;柬r;懽rëࣁgƀlmr⛿✍✔eftĀar০✇ightá৲apsto;柼ightá৽parrowĀlr✥✩efô⓭ight;憬ƀafl✶✹✽r;榅;쀀𝕝us;樭imes;樴š❋❏st;戗áፎƀ;ef❗❘᠀旊nge»❘arĀ;l❤❥䀨t;榓ʀachmt❳❶❼➅➇ròࢨorneòᶌarĀ;d྘➃;業;怎ri;抿̀achiqt➘➝ੀ➢➮➻quo;怹r;쀀𝓁mƀ;egল➪➬;檍;檏Ābu┪➳oĀ;rฟ➹;怚rok;䅂萀<;cdhilqrࠫ⟒☹⟜⟠⟥⟪⟰Āci⟗⟙;檦r;橹reå◲mes;拉arr;楶uest;橻ĀPi⟵⟹ar;榖ƀ;ef⠀भ᠛旃rĀdu⠇⠍shar;楊har;楦Āen⠗⠡rtneqq;쀀≨︀Å⠞܀Dacdefhilnopsu⡀⡅⢂⢎⢓⢠⢥⢨⣚⣢⣤ઃ⣳⤂Dot;戺Ȁclpr⡎⡒⡣⡽r耻¯䂯Āet⡗⡙;時Ā;e⡞⡟朠se»⡟Ā;sျ⡨toȀ;dluျ⡳⡷⡻owîҌefôएðᏑker;斮Āoy⢇⢌mma;権;䐼ash;怔asuredangle»ᘦr;쀀𝔪o;愧ƀcdn⢯⢴⣉ro耻µ䂵Ȁ;acdᑤ⢽⣀⣄sôᚧir;櫰ot肻·Ƶusƀ;bd⣒ᤃ⣓戒Ā;uᴼ⣘;横ţ⣞⣡p;櫛ò−ðઁĀdp⣩⣮els;抧f;쀀𝕞Āct⣸⣽r;쀀𝓂pos»ᖝƀ;lm⤉⤊⤍䎼timap;抸ఀGLRVabcdefghijlmoprstuvw⥂⥓⥾⦉⦘⧚⧩⨕⨚⩘⩝⪃⪕⪤⪨⬄⬇⭄⭿⮮ⰴⱧⱼ⳩Āgt⥇⥋;쀀⋙̸Ā;v⥐௏쀀≫⃒ƀelt⥚⥲⥶ftĀar⥡⥧rrow;懍ightarrow;懎;쀀⋘̸Ā;v⥻ే쀀≪⃒ightarrow;懏ĀDd⦎⦓ash;抯ash;抮ʀbcnpt⦣⦧⦬⦱⧌la»˞ute;䅄g;쀀∠⃒ʀ;Eiop඄⦼⧀⧅⧈;쀀⩰̸d;쀀≋̸s;䅉roø඄urĀ;a⧓⧔普lĀ;s⧓ସǳ⧟\0⧣p肻\xA0ଷmpĀ;e௹ఀʀaeouy⧴⧾⨃⨐⨓ǰ⧹\0⧻;橃on;䅈dil;䅆ngĀ;dൾ⨊ot;쀀⩭̸p;橂;䐽ash;怓΀;Aadqsxஒ⨩⨭⨻⩁⩅⩐rr;懗rĀhr⨳⨶k;椤Ā;oᏲᏰot;쀀≐̸uiöୣĀei⩊⩎ar;椨í஘istĀ;s஠டr;쀀𝔫ȀEest௅⩦⩹⩼ƀ;qs஼⩭௡ƀ;qs஼௅⩴lanô௢ií௪Ā;rஶ⪁»ஷƀAap⪊⪍⪑rò⥱rr;憮ar;櫲ƀ;svྍ⪜ྌĀ;d⪡⪢拼;拺cy;䑚΀AEadest⪷⪺⪾⫂⫅⫶⫹rò⥦;쀀≦̸rr;憚r;急Ȁ;fqs఻⫎⫣⫯tĀar⫔⫙rro÷⫁ightarro÷⪐ƀ;qs఻⪺⫪lanôౕĀ;sౕ⫴»శiíౝĀ;rవ⫾iĀ;eచథiäඐĀpt⬌⬑f;쀀𝕟膀¬;in⬙⬚⬶䂬nȀ;Edvஉ⬤⬨⬮;쀀⋹̸ot;쀀⋵̸ǡஉ⬳⬵;拷;拶iĀ;vಸ⬼ǡಸ⭁⭃;拾;拽ƀaor⭋⭣⭩rȀ;ast୻⭕⭚⭟lleì୻l;쀀⫽⃥;쀀∂̸lint;樔ƀ;ceಒ⭰⭳uåಥĀ;cಘ⭸Ā;eಒ⭽ñಘȀAait⮈⮋⮝⮧rò⦈rrƀ;cw⮔⮕⮙憛;쀀⤳̸;쀀↝̸ghtarrow»⮕riĀ;eೋೖ΀chimpqu⮽⯍⯙⬄୸⯤⯯Ȁ;cerല⯆ഷ⯉uå൅;쀀𝓃ortɭ⬅\0\0⯖ará⭖mĀ;e൮⯟Ā;q൴൳suĀbp⯫⯭å೸åഋƀbcp⯶ⰑⰙȀ;Ees⯿ⰀഢⰄ抄;쀀⫅̸etĀ;eഛⰋqĀ;qണⰀcĀ;eലⰗñസȀ;EesⰢⰣൟⰧ抅;쀀⫆̸etĀ;e൘ⰮqĀ;qൠⰣȀgilrⰽⰿⱅⱇìௗlde耻ñ䃱çృiangleĀlrⱒⱜeftĀ;eచⱚñదightĀ;eೋⱥñ೗Ā;mⱬⱭ䎽ƀ;esⱴⱵⱹ䀣ro;愖p;怇ҀDHadgilrsⲏⲔⲙⲞⲣⲰⲶⳓⳣash;抭arr;椄p;쀀≍⃒ash;抬ĀetⲨⲬ;쀀≥⃒;쀀>⃒nfin;槞ƀAetⲽⳁⳅrr;椂;쀀≤⃒Ā;rⳊⳍ쀀<⃒ie;쀀⊴⃒ĀAtⳘⳜrr;椃rie;쀀⊵⃒im;쀀∼⃒ƀAan⳰⳴ⴂrr;懖rĀhr⳺⳽k;椣Ā;oᏧᏥear;椧ቓ᪕\0\0\0\0\0\0\0\0\0\0\0\0\0ⴭ\0ⴸⵈⵠⵥ⵲ⶄᬇ\0\0ⶍⶫ\0ⷈⷎ\0ⷜ⸙⸫⸾⹃Ācsⴱ᪗ute耻ó䃳ĀiyⴼⵅrĀ;c᪞ⵂ耻ô䃴;䐾ʀabios᪠ⵒⵗǈⵚlac;䅑v;樸old;榼lig;䅓Ācr⵩⵭ir;榿;쀀𝔬ͯ⵹\0\0⵼\0ⶂn;䋛ave耻ò䃲;槁Ābmⶈ෴ar;榵Ȁacitⶕ⶘ⶥⶨrò᪀Āir⶝ⶠr;榾oss;榻nå๒;槀ƀaeiⶱⶵⶹcr;䅍ga;䏉ƀcdnⷀⷅǍron;䎿;榶pf;쀀𝕠ƀaelⷔ⷗ǒr;榷rp;榹΀;adiosvⷪⷫⷮ⸈⸍⸐⸖戨rò᪆Ȁ;efmⷷⷸ⸂⸅橝rĀ;oⷾⷿ愴f»ⷿ耻ª䂪耻º䂺gof;抶r;橖lope;橗;橛ƀclo⸟⸡⸧ò⸁ash耻ø䃸l;折iŬⸯ⸴de耻õ䃵esĀ;aǛ⸺s;樶ml耻ö䃶bar;挽ૡ⹞\0⹽\0⺀⺝\0⺢⺹\0\0⻋ຜ\0⼓\0\0⼫⾼\0⿈rȀ;astЃ⹧⹲຅脀¶;l⹭⹮䂶leìЃɩ⹸\0\0⹻m;櫳;櫽y;䐿rʀcimpt⺋⺏⺓ᡥ⺗nt;䀥od;䀮il;怰enk;怱r;쀀𝔭ƀimo⺨⺰⺴Ā;v⺭⺮䏆;䏕maô੶ne;明ƀ;tv⺿⻀⻈䏀chfork»´;䏖Āau⻏⻟nĀck⻕⻝kĀ;h⇴⻛;愎ö⇴sҀ;abcdemst⻳⻴ᤈ⻹⻽⼄⼆⼊⼎䀫cir;樣ir;樢Āouᵀ⼂;樥;橲n肻±ຝim;樦wo;樧ƀipu⼙⼠⼥ntint;樕f;쀀𝕡nd耻£䂣Ԁ;Eaceinosu່⼿⽁⽄⽇⾁⾉⾒⽾⾶;檳p;檷uå໙Ā;c໎⽌̀;acens່⽙⽟⽦⽨⽾pproø⽃urlyeñ໙ñ໎ƀaes⽯⽶⽺pprox;檹qq;檵im;拨iíໟmeĀ;s⾈ຮ怲ƀEas⽸⾐⽺ð⽵ƀdfp໬⾙⾯ƀals⾠⾥⾪lar;挮ine;挒urf;挓Ā;t໻⾴ï໻rel;抰Āci⿀⿅r;쀀𝓅;䏈ncsp;怈̀fiopsu⿚⋢⿟⿥⿫⿱r;쀀𝔮pf;쀀𝕢rime;恗cr;쀀𝓆ƀaeo⿸〉〓tĀei⿾々rnionóڰnt;樖stĀ;e【】䀿ñἙô༔઀ABHabcdefhilmnoprstux぀けさすムㄎㄫㅇㅢㅲㆎ㈆㈕㈤㈩㉘㉮㉲㊐㊰㊷ƀartぇおがròႳòϝail;検aròᱥar;楤΀cdenqrtとふへみわゔヌĀeuねぱ;쀀∽̱te;䅕iãᅮmptyv;榳gȀ;del࿑らるろ;榒;榥å࿑uo耻»䂻rր;abcfhlpstw࿜ガクシスゼゾダッデナp;極Ā;f࿠ゴs;椠;椳s;椞ë≝ð✮l;楅im;楴l;憣;憝Āaiパフil;椚oĀ;nホボ戶aló༞ƀabrョリヮrò៥rk;杳ĀakンヽcĀekヹ・;䁽;䁝Āes㄂㄄;榌lĀduㄊㄌ;榎;榐Ȁaeuyㄗㄜㄧㄩron;䅙Ādiㄡㄥil;䅗ì࿲âヺ;䑀Ȁclqsㄴㄷㄽㅄa;椷dhar;楩uoĀ;rȎȍh;憳ƀacgㅎㅟངlȀ;ipsླྀㅘㅛႜnåႻarôྩt;断ƀilrㅩဣㅮsht;楽;쀀𝔯ĀaoㅷㆆrĀduㅽㅿ»ѻĀ;l႑ㆄ;楬Ā;vㆋㆌ䏁;䏱ƀgns㆕ㇹㇼht̀ahlrstㆤㆰ㇂㇘㇤㇮rrowĀ;t࿜ㆭaéトarpoonĀduㆻㆿowîㅾp»႒eftĀah㇊㇐rrowó࿪arpoonóՑightarrows;應quigarro÷ニhreetimes;拌g;䋚ingdotseñἲƀahm㈍㈐㈓rò࿪aòՑ;怏oustĀ;a㈞㈟掱che»㈟mid;櫮Ȁabpt㈲㈽㉀㉒Ānr㈷㈺g;柭r;懾rëဃƀafl㉇㉊㉎r;榆;쀀𝕣us;樮imes;樵Āap㉝㉧rĀ;g㉣㉤䀩t;榔olint;樒arò㇣Ȁachq㉻㊀Ⴜ㊅quo;怺r;쀀𝓇Ābu・㊊oĀ;rȔȓƀhir㊗㊛㊠reåㇸmes;拊iȀ;efl㊪ၙᠡ㊫方tri;槎luhar;楨;愞ൡ㋕㋛㋟㌬㌸㍱\0㍺㎤\0\0㏬㏰\0㐨㑈㑚㒭㒱㓊㓱\0㘖\0\0㘳cute;䅛quï➺Ԁ;Eaceinpsyᇭ㋳㋵㋿㌂㌋㌏㌟㌦㌩;檴ǰ㋺\0㋼;檸on;䅡uåᇾĀ;dᇳ㌇il;䅟rc;䅝ƀEas㌖㌘㌛;檶p;檺im;择olint;樓iíሄ;䑁otƀ;be㌴ᵇ㌵担;橦΀Aacmstx㍆㍊㍗㍛㍞㍣㍭rr;懘rĀhr㍐㍒ë∨Ā;oਸ਼਴t耻§䂧i;䀻war;椩mĀin㍩ðnuóñt;朶rĀ;o㍶⁕쀀𝔰Ȁacoy㎂㎆㎑㎠rp;景Āhy㎋㎏cy;䑉;䑈rtɭ㎙\0\0㎜iäᑤaraì⹯耻­䂭Āgm㎨㎴maƀ;fv㎱㎲㎲䏃;䏂Ѐ;deglnprካ㏅㏉㏎㏖㏞㏡㏦ot;橪Ā;q኱ኰĀ;E㏓㏔檞;檠Ā;E㏛㏜檝;檟e;扆lus;樤arr;楲aròᄽȀaeit㏸㐈㐏㐗Āls㏽㐄lsetmé㍪hp;樳parsl;槤Ādlᑣ㐔e;挣Ā;e㐜㐝檪Ā;s㐢㐣檬;쀀⪬︀ƀflp㐮㐳㑂tcy;䑌Ā;b㐸㐹䀯Ā;a㐾㐿槄r;挿f;쀀𝕤aĀdr㑍ЂesĀ;u㑔㑕晠it»㑕ƀcsu㑠㑹㒟Āau㑥㑯pĀ;sᆈ㑫;쀀⊓︀pĀ;sᆴ㑵;쀀⊔︀uĀbp㑿㒏ƀ;esᆗᆜ㒆etĀ;eᆗ㒍ñᆝƀ;esᆨᆭ㒖etĀ;eᆨ㒝ñᆮƀ;afᅻ㒦ְrť㒫ֱ»ᅼaròᅈȀcemt㒹㒾㓂㓅r;쀀𝓈tmîñiì㐕aræᆾĀar㓎㓕rĀ;f㓔ឿ昆Āan㓚㓭ightĀep㓣㓪psiloîỠhé⺯s»⡒ʀbcmnp㓻㕞ሉ㖋㖎Ҁ;Edemnprs㔎㔏㔑㔕㔞㔣㔬㔱㔶抂;櫅ot;檽Ā;dᇚ㔚ot;櫃ult;櫁ĀEe㔨㔪;櫋;把lus;檿arr;楹ƀeiu㔽㕒㕕tƀ;en㔎㕅㕋qĀ;qᇚ㔏eqĀ;q㔫㔨m;櫇Ābp㕚㕜;櫕;櫓c̀;acensᇭ㕬㕲㕹㕻㌦pproø㋺urlyeñᇾñᇳƀaes㖂㖈㌛pproø㌚qñ㌗g;晪ڀ123;Edehlmnps㖩㖬㖯ሜ㖲㖴㗀㗉㗕㗚㗟㗨㗭耻¹䂹耻²䂲耻³䂳;櫆Āos㖹㖼t;檾ub;櫘Ā;dሢ㗅ot;櫄sĀou㗏㗒l;柉b;櫗arr;楻ult;櫂ĀEe㗤㗦;櫌;抋lus;櫀ƀeiu㗴㘉㘌tƀ;enሜ㗼㘂qĀ;qሢ㖲eqĀ;q㗧㗤m;櫈Ābp㘑㘓;櫔;櫖ƀAan㘜㘠㘭rr;懙rĀhr㘦㘨ë∮Ā;oਫ਩war;椪lig耻ß䃟௡㙑㙝㙠ዎ㙳㙹\0㙾㛂\0\0\0\0\0㛛㜃\0㜉㝬\0\0\0㞇ɲ㙖\0\0㙛get;挖;䏄rë๟ƀaey㙦㙫㙰ron;䅥dil;䅣;䑂lrec;挕r;쀀𝔱Ȁeiko㚆㚝㚵㚼ǲ㚋\0㚑eĀ4fኄኁaƀ;sv㚘㚙㚛䎸ym;䏑Ācn㚢㚲kĀas㚨㚮pproø዁im»ኬsðኞĀas㚺㚮ð዁rn耻þ䃾Ǭ̟㛆⋧es膀×;bd㛏㛐㛘䃗Ā;aᤏ㛕r;樱;樰ƀeps㛡㛣㜀á⩍Ȁ;bcf҆㛬㛰㛴ot;挶ir;櫱Ā;o㛹㛼쀀𝕥rk;櫚á㍢rime;怴ƀaip㜏㜒㝤dåቈ΀adempst㜡㝍㝀㝑㝗㝜㝟ngleʀ;dlqr㜰㜱㜶㝀㝂斵own»ᶻeftĀ;e⠀㜾ñम;扜ightĀ;e㊪㝋ñၚot;旬inus;樺lus;樹b;槍ime;樻ezium;揢ƀcht㝲㝽㞁Āry㝷㝻;쀀𝓉;䑆cy;䑛rok;䅧Āio㞋㞎xô᝷headĀlr㞗㞠eftarro÷ࡏightarrow»ཝऀAHabcdfghlmoprstuw㟐㟓㟗㟤㟰㟼㠎㠜㠣㠴㡑㡝㡫㢩㣌㣒㣪㣶ròϭar;楣Ācr㟜㟢ute耻ú䃺òᅐrǣ㟪\0㟭y;䑞ve;䅭Āiy㟵㟺rc耻û䃻;䑃ƀabh㠃㠆㠋ròᎭlac;䅱aòᏃĀir㠓㠘sht;楾;쀀𝔲rave耻ù䃹š㠧㠱rĀlr㠬㠮»ॗ»ႃlk;斀Āct㠹㡍ɯ㠿\0\0㡊rnĀ;e㡅㡆挜r»㡆op;挏ri;旸Āal㡖㡚cr;䅫肻¨͉Āgp㡢㡦on;䅳f;쀀𝕦̀adhlsuᅋ㡸㡽፲㢑㢠ownáᎳarpoonĀlr㢈㢌efô㠭ighô㠯iƀ;hl㢙㢚㢜䏅»ᏺon»㢚parrows;懈ƀcit㢰㣄㣈ɯ㢶\0\0㣁rnĀ;e㢼㢽挝r»㢽op;挎ng;䅯ri;旹cr;쀀𝓊ƀdir㣙㣝㣢ot;拰lde;䅩iĀ;f㜰㣨»᠓Āam㣯㣲rò㢨l耻ü䃼angle;榧ހABDacdeflnoprsz㤜㤟㤩㤭㦵㦸㦽㧟㧤㧨㧳㧹㧽㨁㨠ròϷarĀ;v㤦㤧櫨;櫩asèϡĀnr㤲㤷grt;榜΀eknprst㓣㥆㥋㥒㥝㥤㦖appá␕othinçẖƀhir㓫⻈㥙opô⾵Ā;hᎷ㥢ïㆍĀiu㥩㥭gmá㎳Ābp㥲㦄setneqĀ;q㥽㦀쀀⊊︀;쀀⫋︀setneqĀ;q㦏㦒쀀⊋︀;쀀⫌︀Āhr㦛㦟etá㚜iangleĀlr㦪㦯eft»थight»ၑy;䐲ash»ံƀelr㧄㧒㧗ƀ;beⷪ㧋㧏ar;抻q;扚lip;拮Ābt㧜ᑨaòᑩr;쀀𝔳tré㦮suĀbp㧯㧱»ജ»൙pf;쀀𝕧roð໻tré㦴Ācu㨆㨋r;쀀𝓋Ābp㨐㨘nĀEe㦀㨖»㥾nĀEe㦒㨞»㦐igzag;榚΀cefoprs㨶㨻㩖㩛㩔㩡㩪irc;䅵Ādi㩀㩑Ābg㩅㩉ar;機eĀ;qᗺ㩏;扙erp;愘r;쀀𝔴pf;쀀𝕨Ā;eᑹ㩦atèᑹcr;쀀𝓌ૣណ㪇\0㪋\0㪐㪛\0\0㪝㪨㪫㪯\0\0㫃㫎\0㫘ៜ៟tré៑r;쀀𝔵ĀAa㪔㪗ròσrò৶;䎾ĀAa㪡㪤ròθrò৫að✓is;拻ƀdptឤ㪵㪾Āfl㪺ឩ;쀀𝕩imåឲĀAa㫇㫊ròώròਁĀcq㫒ីr;쀀𝓍Āpt៖㫜ré។Ѐacefiosu㫰㫽㬈㬌㬑㬕㬛㬡cĀuy㫶㫻te耻ý䃽;䑏Āiy㬂㬆rc;䅷;䑋n耻¥䂥r;쀀𝔶cy;䑗pf;쀀𝕪cr;쀀𝓎Ācm㬦㬩y;䑎l耻ÿ䃿Ԁacdefhiosw㭂㭈㭔㭘㭤㭩㭭㭴㭺㮀cute;䅺Āay㭍㭒ron;䅾;䐷ot;䅼Āet㭝㭡træᕟa;䎶r;쀀𝔷cy;䐶grarr;懝pf;쀀𝕫cr;쀀𝓏Ājn㮅㮇;怍j;怌".split("").map((c) => c.charCodeAt(0)));
//#endregion
//#region node_modules/entities/lib/esm/generated/decode-data-xml.js
var decode_data_xml_default = new Uint16Array("Ȁaglq	\x1Bɭ\0\0p;䀦os;䀧t;䀾t;䀼uot;䀢".split("").map((c) => c.charCodeAt(0)));
//#endregion
//#region node_modules/entities/lib/esm/decode_codepoint.js
var _a;
var decodeMap = /* @__PURE__ */ new Map([
	[0, 65533],
	[128, 8364],
	[130, 8218],
	[131, 402],
	[132, 8222],
	[133, 8230],
	[134, 8224],
	[135, 8225],
	[136, 710],
	[137, 8240],
	[138, 352],
	[139, 8249],
	[140, 338],
	[142, 381],
	[145, 8216],
	[146, 8217],
	[147, 8220],
	[148, 8221],
	[149, 8226],
	[150, 8211],
	[151, 8212],
	[152, 732],
	[153, 8482],
	[154, 353],
	[155, 8250],
	[156, 339],
	[158, 382],
	[159, 376]
]);
/**
* Polyfill for `String.fromCodePoint`. It is used to create a string from a Unicode code point.
*/
var fromCodePoint$1 = (_a = String.fromCodePoint) !== null && _a !== void 0 ? _a : function(codePoint) {
	let output = "";
	if (codePoint > 65535) {
		codePoint -= 65536;
		output += String.fromCharCode(codePoint >>> 10 & 1023 | 55296);
		codePoint = 56320 | codePoint & 1023;
	}
	output += String.fromCharCode(codePoint);
	return output;
};
/**
* Replace the given code point with a replacement character if it is a
* surrogate or is outside the valid range. Otherwise return the code
* point unchanged.
*/
function replaceCodePoint(codePoint) {
	var _a;
	if (codePoint >= 55296 && codePoint <= 57343 || codePoint > 1114111) return 65533;
	return (_a = decodeMap.get(codePoint)) !== null && _a !== void 0 ? _a : codePoint;
}
//#endregion
//#region node_modules/entities/lib/esm/decode.js
var CharCodes;
(function(CharCodes) {
	CharCodes[CharCodes["NUM"] = 35] = "NUM";
	CharCodes[CharCodes["SEMI"] = 59] = "SEMI";
	CharCodes[CharCodes["EQUALS"] = 61] = "EQUALS";
	CharCodes[CharCodes["ZERO"] = 48] = "ZERO";
	CharCodes[CharCodes["NINE"] = 57] = "NINE";
	CharCodes[CharCodes["LOWER_A"] = 97] = "LOWER_A";
	CharCodes[CharCodes["LOWER_F"] = 102] = "LOWER_F";
	CharCodes[CharCodes["LOWER_X"] = 120] = "LOWER_X";
	CharCodes[CharCodes["LOWER_Z"] = 122] = "LOWER_Z";
	CharCodes[CharCodes["UPPER_A"] = 65] = "UPPER_A";
	CharCodes[CharCodes["UPPER_F"] = 70] = "UPPER_F";
	CharCodes[CharCodes["UPPER_Z"] = 90] = "UPPER_Z";
})(CharCodes || (CharCodes = {}));
/** Bit that needs to be set to convert an upper case ASCII character to lower case */
var TO_LOWER_BIT = 32;
var BinTrieFlags;
(function(BinTrieFlags) {
	BinTrieFlags[BinTrieFlags["VALUE_LENGTH"] = 49152] = "VALUE_LENGTH";
	BinTrieFlags[BinTrieFlags["BRANCH_LENGTH"] = 16256] = "BRANCH_LENGTH";
	BinTrieFlags[BinTrieFlags["JUMP_TABLE"] = 127] = "JUMP_TABLE";
})(BinTrieFlags || (BinTrieFlags = {}));
function isNumber(code) {
	return code >= CharCodes.ZERO && code <= CharCodes.NINE;
}
function isHexadecimalCharacter(code) {
	return code >= CharCodes.UPPER_A && code <= CharCodes.UPPER_F || code >= CharCodes.LOWER_A && code <= CharCodes.LOWER_F;
}
function isAsciiAlphaNumeric(code) {
	return code >= CharCodes.UPPER_A && code <= CharCodes.UPPER_Z || code >= CharCodes.LOWER_A && code <= CharCodes.LOWER_Z || isNumber(code);
}
/**
* Checks if the given character is a valid end character for an entity in an attribute.
*
* Attribute values that aren't terminated properly aren't parsed, and shouldn't lead to a parser error.
* See the example in https://html.spec.whatwg.org/multipage/parsing.html#named-character-reference-state
*/
function isEntityInAttributeInvalidEnd(code) {
	return code === CharCodes.EQUALS || isAsciiAlphaNumeric(code);
}
var EntityDecoderState;
(function(EntityDecoderState) {
	EntityDecoderState[EntityDecoderState["EntityStart"] = 0] = "EntityStart";
	EntityDecoderState[EntityDecoderState["NumericStart"] = 1] = "NumericStart";
	EntityDecoderState[EntityDecoderState["NumericDecimal"] = 2] = "NumericDecimal";
	EntityDecoderState[EntityDecoderState["NumericHex"] = 3] = "NumericHex";
	EntityDecoderState[EntityDecoderState["NamedEntity"] = 4] = "NamedEntity";
})(EntityDecoderState || (EntityDecoderState = {}));
var DecodingMode;
(function(DecodingMode) {
	/** Entities in text nodes that can end with any character. */
	DecodingMode[DecodingMode["Legacy"] = 0] = "Legacy";
	/** Only allow entities terminated with a semicolon. */
	DecodingMode[DecodingMode["Strict"] = 1] = "Strict";
	/** Entities in attributes have limitations on ending characters. */
	DecodingMode[DecodingMode["Attribute"] = 2] = "Attribute";
})(DecodingMode || (DecodingMode = {}));
/**
* Token decoder with support of writing partial entities.
*/
var EntityDecoder = class {
	constructor(decodeTree, emitCodePoint, errors) {
		this.decodeTree = decodeTree;
		this.emitCodePoint = emitCodePoint;
		this.errors = errors;
		/** The current state of the decoder. */
		this.state = EntityDecoderState.EntityStart;
		/** Characters that were consumed while parsing an entity. */
		this.consumed = 1;
		/**
		* The result of the entity.
		*
		* Either the result index of a numeric entity, or the codepoint of a
		* numeric entity.
		*/
		this.result = 0;
		/** The current index in the decode tree. */
		this.treeIndex = 0;
		/** The number of characters that were consumed in excess. */
		this.excess = 1;
		/** The mode in which the decoder is operating. */
		this.decodeMode = DecodingMode.Strict;
	}
	/** Resets the instance to make it reusable. */
	startEntity(decodeMode) {
		this.decodeMode = decodeMode;
		this.state = EntityDecoderState.EntityStart;
		this.result = 0;
		this.treeIndex = 0;
		this.excess = 1;
		this.consumed = 1;
	}
	/**
	* Write an entity to the decoder. This can be called multiple times with partial entities.
	* If the entity is incomplete, the decoder will return -1.
	*
	* Mirrors the implementation of `getDecoder`, but with the ability to stop decoding if the
	* entity is incomplete, and resume when the next string is written.
	*
	* @param string The string containing the entity (or a continuation of the entity).
	* @param offset The offset at which the entity begins. Should be 0 if this is not the first call.
	* @returns The number of characters that were consumed, or -1 if the entity is incomplete.
	*/
	write(str, offset) {
		switch (this.state) {
			case EntityDecoderState.EntityStart:
				if (str.charCodeAt(offset) === CharCodes.NUM) {
					this.state = EntityDecoderState.NumericStart;
					this.consumed += 1;
					return this.stateNumericStart(str, offset + 1);
				}
				this.state = EntityDecoderState.NamedEntity;
				return this.stateNamedEntity(str, offset);
			case EntityDecoderState.NumericStart: return this.stateNumericStart(str, offset);
			case EntityDecoderState.NumericDecimal: return this.stateNumericDecimal(str, offset);
			case EntityDecoderState.NumericHex: return this.stateNumericHex(str, offset);
			case EntityDecoderState.NamedEntity: return this.stateNamedEntity(str, offset);
		}
	}
	/**
	* Switches between the numeric decimal and hexadecimal states.
	*
	* Equivalent to the `Numeric character reference state` in the HTML spec.
	*
	* @param str The string containing the entity (or a continuation of the entity).
	* @param offset The current offset.
	* @returns The number of characters that were consumed, or -1 if the entity is incomplete.
	*/
	stateNumericStart(str, offset) {
		if (offset >= str.length) return -1;
		if ((str.charCodeAt(offset) | TO_LOWER_BIT) === CharCodes.LOWER_X) {
			this.state = EntityDecoderState.NumericHex;
			this.consumed += 1;
			return this.stateNumericHex(str, offset + 1);
		}
		this.state = EntityDecoderState.NumericDecimal;
		return this.stateNumericDecimal(str, offset);
	}
	addToNumericResult(str, start, end, base) {
		if (start !== end) {
			const digitCount = end - start;
			this.result = this.result * Math.pow(base, digitCount) + parseInt(str.substr(start, digitCount), base);
			this.consumed += digitCount;
		}
	}
	/**
	* Parses a hexadecimal numeric entity.
	*
	* Equivalent to the `Hexademical character reference state` in the HTML spec.
	*
	* @param str The string containing the entity (or a continuation of the entity).
	* @param offset The current offset.
	* @returns The number of characters that were consumed, or -1 if the entity is incomplete.
	*/
	stateNumericHex(str, offset) {
		const startIdx = offset;
		while (offset < str.length) {
			const char = str.charCodeAt(offset);
			if (isNumber(char) || isHexadecimalCharacter(char)) offset += 1;
			else {
				this.addToNumericResult(str, startIdx, offset, 16);
				return this.emitNumericEntity(char, 3);
			}
		}
		this.addToNumericResult(str, startIdx, offset, 16);
		return -1;
	}
	/**
	* Parses a decimal numeric entity.
	*
	* Equivalent to the `Decimal character reference state` in the HTML spec.
	*
	* @param str The string containing the entity (or a continuation of the entity).
	* @param offset The current offset.
	* @returns The number of characters that were consumed, or -1 if the entity is incomplete.
	*/
	stateNumericDecimal(str, offset) {
		const startIdx = offset;
		while (offset < str.length) {
			const char = str.charCodeAt(offset);
			if (isNumber(char)) offset += 1;
			else {
				this.addToNumericResult(str, startIdx, offset, 10);
				return this.emitNumericEntity(char, 2);
			}
		}
		this.addToNumericResult(str, startIdx, offset, 10);
		return -1;
	}
	/**
	* Validate and emit a numeric entity.
	*
	* Implements the logic from the `Hexademical character reference start
	* state` and `Numeric character reference end state` in the HTML spec.
	*
	* @param lastCp The last code point of the entity. Used to see if the
	*               entity was terminated with a semicolon.
	* @param expectedLength The minimum number of characters that should be
	*                       consumed. Used to validate that at least one digit
	*                       was consumed.
	* @returns The number of characters that were consumed.
	*/
	emitNumericEntity(lastCp, expectedLength) {
		var _a;
		if (this.consumed <= expectedLength) {
			(_a = this.errors) === null || _a === void 0 || _a.absenceOfDigitsInNumericCharacterReference(this.consumed);
			return 0;
		}
		if (lastCp === CharCodes.SEMI) this.consumed += 1;
		else if (this.decodeMode === DecodingMode.Strict) return 0;
		this.emitCodePoint(replaceCodePoint(this.result), this.consumed);
		if (this.errors) {
			if (lastCp !== CharCodes.SEMI) this.errors.missingSemicolonAfterCharacterReference();
			this.errors.validateNumericCharacterReference(this.result);
		}
		return this.consumed;
	}
	/**
	* Parses a named entity.
	*
	* Equivalent to the `Named character reference state` in the HTML spec.
	*
	* @param str The string containing the entity (or a continuation of the entity).
	* @param offset The current offset.
	* @returns The number of characters that were consumed, or -1 if the entity is incomplete.
	*/
	stateNamedEntity(str, offset) {
		const { decodeTree } = this;
		let current = decodeTree[this.treeIndex];
		let valueLength = (current & BinTrieFlags.VALUE_LENGTH) >> 14;
		for (; offset < str.length; offset++, this.excess++) {
			const char = str.charCodeAt(offset);
			this.treeIndex = determineBranch(decodeTree, current, this.treeIndex + Math.max(1, valueLength), char);
			if (this.treeIndex < 0) return this.result === 0 || this.decodeMode === DecodingMode.Attribute && (valueLength === 0 || isEntityInAttributeInvalidEnd(char)) ? 0 : this.emitNotTerminatedNamedEntity();
			current = decodeTree[this.treeIndex];
			valueLength = (current & BinTrieFlags.VALUE_LENGTH) >> 14;
			if (valueLength !== 0) {
				if (char === CharCodes.SEMI) return this.emitNamedEntityData(this.treeIndex, valueLength, this.consumed + this.excess);
				if (this.decodeMode !== DecodingMode.Strict) {
					this.result = this.treeIndex;
					this.consumed += this.excess;
					this.excess = 0;
				}
			}
		}
		return -1;
	}
	/**
	* Emit a named entity that was not terminated with a semicolon.
	*
	* @returns The number of characters consumed.
	*/
	emitNotTerminatedNamedEntity() {
		var _a;
		const { result, decodeTree } = this;
		const valueLength = (decodeTree[result] & BinTrieFlags.VALUE_LENGTH) >> 14;
		this.emitNamedEntityData(result, valueLength, this.consumed);
		(_a = this.errors) === null || _a === void 0 || _a.missingSemicolonAfterCharacterReference();
		return this.consumed;
	}
	/**
	* Emit a named entity.
	*
	* @param result The index of the entity in the decode tree.
	* @param valueLength The number of bytes in the entity.
	* @param consumed The number of characters consumed.
	*
	* @returns The number of characters consumed.
	*/
	emitNamedEntityData(result, valueLength, consumed) {
		const { decodeTree } = this;
		this.emitCodePoint(valueLength === 1 ? decodeTree[result] & ~BinTrieFlags.VALUE_LENGTH : decodeTree[result + 1], consumed);
		if (valueLength === 3) this.emitCodePoint(decodeTree[result + 2], consumed);
		return consumed;
	}
	/**
	* Signal to the parser that the end of the input was reached.
	*
	* Remaining data will be emitted and relevant errors will be produced.
	*
	* @returns The number of characters consumed.
	*/
	end() {
		var _a;
		switch (this.state) {
			case EntityDecoderState.NamedEntity: return this.result !== 0 && (this.decodeMode !== DecodingMode.Attribute || this.result === this.treeIndex) ? this.emitNotTerminatedNamedEntity() : 0;
			case EntityDecoderState.NumericDecimal: return this.emitNumericEntity(0, 2);
			case EntityDecoderState.NumericHex: return this.emitNumericEntity(0, 3);
			case EntityDecoderState.NumericStart:
				(_a = this.errors) === null || _a === void 0 || _a.absenceOfDigitsInNumericCharacterReference(this.consumed);
				return 0;
			case EntityDecoderState.EntityStart: return 0;
		}
	}
};
/**
* Creates a function that decodes entities in a string.
*
* @param decodeTree The decode tree.
* @returns A function that decodes entities in a string.
*/
function getDecoder(decodeTree) {
	let ret = "";
	const decoder = new EntityDecoder(decodeTree, (str) => ret += fromCodePoint$1(str));
	return function decodeWithTrie(str, decodeMode) {
		let lastIndex = 0;
		let offset = 0;
		while ((offset = str.indexOf("&", offset)) >= 0) {
			ret += str.slice(lastIndex, offset);
			decoder.startEntity(decodeMode);
			const len = decoder.write(str, offset + 1);
			if (len < 0) {
				lastIndex = offset + decoder.end();
				break;
			}
			lastIndex = offset + len;
			offset = len === 0 ? lastIndex + 1 : lastIndex;
		}
		const result = ret + str.slice(lastIndex);
		ret = "";
		return result;
	};
}
/**
* Determines the branch of the current node that is taken given the current
* character. This function is used to traverse the trie.
*
* @param decodeTree The trie.
* @param current The current node.
* @param nodeIdx The index right after the current node and its value.
* @param char The current character.
* @returns The index of the next node, or -1 if no branch is taken.
*/
function determineBranch(decodeTree, current, nodeIdx, char) {
	const branchCount = (current & BinTrieFlags.BRANCH_LENGTH) >> 7;
	const jumpOffset = current & BinTrieFlags.JUMP_TABLE;
	if (branchCount === 0) return jumpOffset !== 0 && char === jumpOffset ? nodeIdx : -1;
	if (jumpOffset) {
		const value = char - jumpOffset;
		return value < 0 || value >= branchCount ? -1 : decodeTree[nodeIdx + value] - 1;
	}
	let lo = nodeIdx;
	let hi = lo + branchCount - 1;
	while (lo <= hi) {
		const mid = lo + hi >>> 1;
		const midVal = decodeTree[mid];
		if (midVal < char) lo = mid + 1;
		else if (midVal > char) hi = mid - 1;
		else return decodeTree[mid + branchCount];
	}
	return -1;
}
var htmlDecoder = getDecoder(decode_data_html_default);
getDecoder(decode_data_xml_default);
/**
* Decodes an HTML string.
*
* @param str The string to decode.
* @param mode The decoding mode.
* @returns The decoded string.
*/
function decodeHTML(str, mode = DecodingMode.Legacy) {
	return htmlDecoder(str, mode);
}
/**
* Decodes an HTML string, requiring all entities to be terminated by a semicolon.
*
* @param str The string to decode.
* @returns The decoded string.
*/
function decodeHTMLStrict(str) {
	return htmlDecoder(str, DecodingMode.Strict);
}
//#endregion
//#region node_modules/markdown-it/lib/common/utils.mjs
var utils_exports = /* @__PURE__ */ __exportAll({
	arrayReplaceAt: () => arrayReplaceAt,
	asciiTrim: () => asciiTrim,
	assign: () => assign$1,
	escapeHtml: () => escapeHtml,
	escapeRE: () => escapeRE$1,
	fromCodePoint: () => fromCodePoint,
	has: () => has,
	isMdAsciiPunct: () => isMdAsciiPunct,
	isPunctChar: () => isPunctChar,
	isPunctCharCode: () => isPunctCharCode,
	isSpace: () => isSpace,
	isString: () => isString$1,
	isValidEntityCode: () => isValidEntityCode,
	isWhiteSpace: () => isWhiteSpace,
	lib: () => lib,
	normalizeReference: () => normalizeReference,
	unescapeAll: () => unescapeAll,
	unescapeMd: () => unescapeMd
});
function _class$1(obj) {
	return Object.prototype.toString.call(obj);
}
function isString$1(obj) {
	return _class$1(obj) === "[object String]";
}
var _hasOwnProperty = Object.prototype.hasOwnProperty;
function has(object, key) {
	return _hasOwnProperty.call(object, key);
}
function assign$1(obj) {
	Array.prototype.slice.call(arguments, 1).forEach(function(source) {
		if (!source) return;
		if (typeof source !== "object") throw new TypeError(source + "must be object");
		Object.keys(source).forEach(function(key) {
			obj[key] = source[key];
		});
	});
	return obj;
}
function arrayReplaceAt(src, pos, newElements) {
	return [].concat(src.slice(0, pos), newElements, src.slice(pos + 1));
}
function isValidEntityCode(c) {
	if (c >= 55296 && c <= 57343) return false;
	if (c >= 64976 && c <= 65007) return false;
	if ((c & 65535) === 65535 || (c & 65535) === 65534) return false;
	if (c >= 0 && c <= 8) return false;
	if (c === 11) return false;
	if (c >= 14 && c <= 31) return false;
	if (c >= 127 && c <= 159) return false;
	if (c > 1114111) return false;
	return true;
}
function fromCodePoint(c) {
	if (c > 65535) {
		c -= 65536;
		const surrogate1 = 55296 + (c >> 10);
		const surrogate2 = 56320 + (c & 1023);
		return String.fromCharCode(surrogate1, surrogate2);
	}
	return String.fromCharCode(c);
}
var UNESCAPE_MD_RE = /\\([!"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~])/g;
var UNESCAPE_ALL_RE = new RegExp(UNESCAPE_MD_RE.source + "|" + /&([a-z#][a-z0-9]{1,31});/gi.source, "gi");
var DIGITAL_ENTITY_TEST_RE = /^#((?:x[a-f0-9]{1,8}|[0-9]{1,8}))$/i;
function replaceEntityPattern(match, name) {
	if (name.charCodeAt(0) === 35 && DIGITAL_ENTITY_TEST_RE.test(name)) {
		const code = name[1].toLowerCase() === "x" ? parseInt(name.slice(2), 16) : parseInt(name.slice(1), 10);
		if (isValidEntityCode(code)) return fromCodePoint(code);
		return match;
	}
	const decoded = decodeHTML(match);
	if (decoded !== match) return decoded;
	return match;
}
function unescapeMd(str) {
	if (str.indexOf("\\") < 0) return str;
	return str.replace(UNESCAPE_MD_RE, "$1");
}
function unescapeAll(str) {
	if (str.indexOf("\\") < 0 && str.indexOf("&") < 0) return str;
	return str.replace(UNESCAPE_ALL_RE, function(match, escaped, entity) {
		if (escaped) return escaped;
		return replaceEntityPattern(match, entity);
	});
}
var HTML_ESCAPE_TEST_RE = /[&<>"]/;
var HTML_ESCAPE_REPLACE_RE = /[&<>"]/g;
var HTML_REPLACEMENTS = {
	"&": "&amp;",
	"<": "&lt;",
	">": "&gt;",
	"\"": "&quot;"
};
function replaceUnsafeChar(ch) {
	return HTML_REPLACEMENTS[ch];
}
function escapeHtml(str) {
	if (HTML_ESCAPE_TEST_RE.test(str)) return str.replace(HTML_ESCAPE_REPLACE_RE, replaceUnsafeChar);
	return str;
}
var REGEXP_ESCAPE_RE = /[.?*+^$[\]\\(){}|-]/g;
function escapeRE$1(str) {
	return str.replace(REGEXP_ESCAPE_RE, "\\$&");
}
function isSpace(code) {
	switch (code) {
		case 9:
		case 32: return true;
	}
	return false;
}
function isWhiteSpace(code) {
	if (code >= 8192 && code <= 8202) return true;
	switch (code) {
		case 9:
		case 10:
		case 11:
		case 12:
		case 13:
		case 32:
		case 160:
		case 5760:
		case 8239:
		case 8287:
		case 12288: return true;
	}
	return false;
}
function isPunctChar(ch) {
	return regex_default$2.test(ch) || regex_default$1.test(ch);
}
function isPunctCharCode(code) {
	return isPunctChar(fromCodePoint(code));
}
function isMdAsciiPunct(ch) {
	switch (ch) {
		case 33:
		case 34:
		case 35:
		case 36:
		case 37:
		case 38:
		case 39:
		case 40:
		case 41:
		case 42:
		case 43:
		case 44:
		case 45:
		case 46:
		case 47:
		case 58:
		case 59:
		case 60:
		case 61:
		case 62:
		case 63:
		case 64:
		case 91:
		case 92:
		case 93:
		case 94:
		case 95:
		case 96:
		case 123:
		case 124:
		case 125:
		case 126: return true;
		default: return false;
	}
}
function normalizeReference(str) {
	str = str.trim().replace(/\s+/g, " ");
	if ("ẞ".toLowerCase() === "Ṿ")
 /* c8 ignore next 2 */
	str = str.replace(/ẞ/g, "ß");
	return str.toLowerCase().toUpperCase();
}
function isAsciiTrimmable(c) {
	return c === 32 || c === 9 || c === 10 || c === 13;
}
function asciiTrim(str) {
	let start = 0;
	for (; start < str.length; start++) if (!isAsciiTrimmable(str.charCodeAt(start))) break;
	let end = str.length - 1;
	for (; end >= start; end--) if (!isAsciiTrimmable(str.charCodeAt(end))) break;
	return str.slice(start, end + 1);
}
var lib = {
	mdurl: mdurl_exports,
	ucmicro: uc_micro_exports
};
//#endregion
//#region node_modules/markdown-it/lib/helpers/parse_link_label.mjs
function parseLinkLabel(state, start, disableNested) {
	let level, found, marker, prevPos;
	const max = state.posMax;
	const oldPos = state.pos;
	state.pos = start + 1;
	level = 1;
	while (state.pos < max) {
		marker = state.src.charCodeAt(state.pos);
		if (marker === 93) {
			level--;
			if (level === 0) {
				found = true;
				break;
			}
		}
		prevPos = state.pos;
		state.md.inline.skipToken(state);
		if (marker === 91) {
			if (prevPos === state.pos - 1) level++;
			else if (disableNested) {
				state.pos = oldPos;
				return -1;
			}
		}
	}
	let labelEnd = -1;
	if (found) labelEnd = state.pos;
	state.pos = oldPos;
	return labelEnd;
}
//#endregion
//#region node_modules/markdown-it/lib/helpers/parse_link_destination.mjs
function parseLinkDestination(str, start, max) {
	let code;
	let pos = start;
	const result = {
		ok: false,
		pos: 0,
		str: ""
	};
	if (str.charCodeAt(pos) === 60) {
		pos++;
		while (pos < max) {
			code = str.charCodeAt(pos);
			if (code === 10) return result;
			if (code === 60) return result;
			if (code === 62) {
				result.pos = pos + 1;
				result.str = unescapeAll(str.slice(start + 1, pos));
				result.ok = true;
				return result;
			}
			if (code === 92 && pos + 1 < max) {
				pos += 2;
				continue;
			}
			pos++;
		}
		return result;
	}
	let level = 0;
	while (pos < max) {
		code = str.charCodeAt(pos);
		if (code === 32) break;
		if (code < 32 || code === 127) break;
		if (code === 92 && pos + 1 < max) {
			if (str.charCodeAt(pos + 1) === 32) {
				pos++;
				continue;
			}
			pos += 2;
			continue;
		}
		if (code === 40) {
			level++;
			if (level > 32) return result;
		}
		if (code === 41) {
			if (level === 0) break;
			level--;
		}
		pos++;
	}
	if (start === pos) return result;
	if (level !== 0) return result;
	result.str = unescapeAll(str.slice(start, pos));
	result.pos = pos;
	result.ok = true;
	return result;
}
//#endregion
//#region node_modules/markdown-it/lib/helpers/parse_link_title.mjs
function parseLinkTitle(str, start, max, prev_state) {
	let code;
	let pos = start;
	const state = {
		ok: false,
		can_continue: false,
		pos: 0,
		str: "",
		marker: 0
	};
	if (prev_state) {
		state.str = prev_state.str;
		state.marker = prev_state.marker;
	} else {
		if (pos >= max) return state;
		let marker = str.charCodeAt(pos);
		if (marker !== 34 && marker !== 39 && marker !== 40) return state;
		start++;
		pos++;
		if (marker === 40) marker = 41;
		state.marker = marker;
	}
	while (pos < max) {
		code = str.charCodeAt(pos);
		if (code === state.marker) {
			state.pos = pos + 1;
			state.str += unescapeAll(str.slice(start, pos));
			state.ok = true;
			return state;
		} else if (code === 40 && state.marker === 41) return state;
		else if (code === 92 && pos + 1 < max) pos++;
		pos++;
	}
	state.can_continue = true;
	state.str += unescapeAll(str.slice(start, pos));
	return state;
}
//#endregion
//#region node_modules/markdown-it/lib/helpers/index.mjs
var helpers_exports = /* @__PURE__ */ __exportAll({
	parseLinkDestination: () => parseLinkDestination,
	parseLinkLabel: () => parseLinkLabel,
	parseLinkTitle: () => parseLinkTitle
});
//#endregion
//#region node_modules/markdown-it/lib/renderer.mjs
/**
* class Renderer
*
* Generates HTML from parsed token stream. Each instance has independent
* copy of rules. Those can be rewritten with ease. Also, you can add new
* rules if you create plugin and adds new token types.
**/
var default_rules = {};
default_rules.code_inline = function(tokens, idx, options, env, slf) {
	const token = tokens[idx];
	return "<code" + slf.renderAttrs(token) + ">" + escapeHtml(token.content) + "</code>";
};
default_rules.code_block = function(tokens, idx, options, env, slf) {
	const token = tokens[idx];
	return "<pre" + slf.renderAttrs(token) + "><code>" + escapeHtml(tokens[idx].content) + "</code></pre>\n";
};
default_rules.fence = function(tokens, idx, options, env, slf) {
	const token = tokens[idx];
	const info = token.info ? unescapeAll(token.info).trim() : "";
	let langName = "";
	let langAttrs = "";
	if (info) {
		const arr = info.split(/(\s+)/g);
		langName = arr[0];
		langAttrs = arr.slice(2).join("");
	}
	let highlighted;
	if (options.highlight) highlighted = options.highlight(token.content, langName, langAttrs) || escapeHtml(token.content);
	else highlighted = escapeHtml(token.content);
	if (highlighted.indexOf("<pre") === 0) return highlighted + "\n";
	if (info) {
		const i = token.attrIndex("class");
		const tmpAttrs = token.attrs ? token.attrs.slice() : [];
		if (i < 0) tmpAttrs.push(["class", options.langPrefix + langName]);
		else {
			tmpAttrs[i] = tmpAttrs[i].slice();
			tmpAttrs[i][1] += " " + options.langPrefix + langName;
		}
		const tmpToken = { attrs: tmpAttrs };
		return `<pre><code${slf.renderAttrs(tmpToken)}>${highlighted}</code></pre>\n`;
	}
	return `<pre><code${slf.renderAttrs(token)}>${highlighted}</code></pre>\n`;
};
default_rules.image = function(tokens, idx, options, env, slf) {
	const token = tokens[idx];
	token.attrs[token.attrIndex("alt")][1] = slf.renderInlineAsText(token.children, options, env);
	return slf.renderToken(tokens, idx, options);
};
default_rules.hardbreak = function(tokens, idx, options) {
	return options.xhtmlOut ? "<br />\n" : "<br>\n";
};
default_rules.softbreak = function(tokens, idx, options) {
	return options.breaks ? options.xhtmlOut ? "<br />\n" : "<br>\n" : "\n";
};
default_rules.text = function(tokens, idx) {
	return escapeHtml(tokens[idx].content);
};
default_rules.html_block = function(tokens, idx) {
	return tokens[idx].content;
};
default_rules.html_inline = function(tokens, idx) {
	return tokens[idx].content;
};
/**
* new Renderer()
*
* Creates new [[Renderer]] instance and fill [[Renderer#rules]] with defaults.
**/
function Renderer() {
	/**
	* Renderer#rules -> Object
	*
	* Contains render rules for tokens. Can be updated and extended.
	*
	* ##### Example
	*
	* ```javascript
	* var md = require('markdown-it')();
	*
	* md.renderer.rules.strong_open  = function () { return '<b>'; };
	* md.renderer.rules.strong_close = function () { return '</b>'; };
	*
	* var result = md.renderInline(...);
	* ```
	*
	* Each rule is called as independent static function with fixed signature:
	*
	* ```javascript
	* function my_token_render(tokens, idx, options, env, renderer) {
	*   // ...
	*   return renderedHTML;
	* }
	* ```
	*
	* See [source code](https://github.com/markdown-it/markdown-it/blob/master/lib/renderer.mjs)
	* for more details and examples.
	**/
	this.rules = assign$1({}, default_rules);
}
/**
* Renderer.renderAttrs(token) -> String
*
* Render token attributes to string.
**/
Renderer.prototype.renderAttrs = function renderAttrs(token) {
	let i, l, result;
	if (!token.attrs) return "";
	result = "";
	for (i = 0, l = token.attrs.length; i < l; i++) result += " " + escapeHtml(token.attrs[i][0]) + "=\"" + escapeHtml(token.attrs[i][1]) + "\"";
	return result;
};
/**
* Renderer.renderToken(tokens, idx, options) -> String
* - tokens (Array): list of tokens
* - idx (Numbed): token index to render
* - options (Object): params of parser instance
*
* Default token renderer. Can be overriden by custom function
* in [[Renderer#rules]].
**/
Renderer.prototype.renderToken = function renderToken(tokens, idx, options) {
	const token = tokens[idx];
	let result = "";
	if (token.hidden) return "";
	if (token.block && token.nesting !== -1 && idx && tokens[idx - 1].hidden) result += "\n";
	result += (token.nesting === -1 ? "</" : "<") + token.tag;
	result += this.renderAttrs(token);
	if (token.nesting === 0 && options.xhtmlOut) result += " /";
	let needLf = false;
	if (token.block) {
		needLf = true;
		if (token.nesting === 1) {
			if (idx + 1 < tokens.length) {
				const nextToken = tokens[idx + 1];
				if (nextToken.type === "inline" || nextToken.hidden) needLf = false;
				else if (nextToken.nesting === -1 && nextToken.tag === token.tag) needLf = false;
			}
		}
	}
	result += needLf ? ">\n" : ">";
	return result;
};
/**
* Renderer.renderInline(tokens, options, env) -> String
* - tokens (Array): list on block tokens to render
* - options (Object): params of parser instance
* - env (Object): additional data from parsed input (references, for example)
*
* The same as [[Renderer.render]], but for single token of `inline` type.
**/
Renderer.prototype.renderInline = function(tokens, options, env) {
	let result = "";
	const rules = this.rules;
	for (let i = 0, len = tokens.length; i < len; i++) {
		const type = tokens[i].type;
		if (typeof rules[type] !== "undefined") result += rules[type](tokens, i, options, env, this);
		else result += this.renderToken(tokens, i, options);
	}
	return result;
};
/** internal
* Renderer.renderInlineAsText(tokens, options, env) -> String
* - tokens (Array): list on block tokens to render
* - options (Object): params of parser instance
* - env (Object): additional data from parsed input (references, for example)
*
* Special kludge for image `alt` attributes to conform CommonMark spec.
* Don't try to use it! Spec requires to show `alt` content with stripped markup,
* instead of simple escaping.
**/
Renderer.prototype.renderInlineAsText = function(tokens, options, env) {
	let result = "";
	for (let i = 0, len = tokens.length; i < len; i++) switch (tokens[i].type) {
		case "text":
			result += tokens[i].content;
			break;
		case "image":
			result += this.renderInlineAsText(tokens[i].children, options, env);
			break;
		case "html_inline":
		case "html_block":
			result += tokens[i].content;
			break;
		case "softbreak":
		case "hardbreak":
			result += "\n";
			break;
		default:
	}
	return result;
};
/**
* Renderer.render(tokens, options, env) -> String
* - tokens (Array): list on block tokens to render
* - options (Object): params of parser instance
* - env (Object): additional data from parsed input (references, for example)
*
* Takes token stream and generates HTML. Probably, you will never need to call
* this method directly.
**/
Renderer.prototype.render = function(tokens, options, env) {
	let result = "";
	const rules = this.rules;
	for (let i = 0, len = tokens.length; i < len; i++) {
		const type = tokens[i].type;
		if (type === "inline") result += this.renderInline(tokens[i].children, options, env);
		else if (typeof rules[type] !== "undefined") result += rules[type](tokens, i, options, env, this);
		else result += this.renderToken(tokens, i, options, env);
	}
	return result;
};
//#endregion
//#region node_modules/markdown-it/lib/ruler.mjs
/**
* class Ruler
*
* Helper class, used by [[MarkdownIt#core]], [[MarkdownIt#block]] and
* [[MarkdownIt#inline]] to manage sequences of functions (rules):
*
* - keep rules in defined order
* - assign the name to each rule
* - enable/disable rules
* - add/replace rules
* - allow assign rules to additional named chains (in the same)
* - cacheing lists of active rules
*
* You will not need use this class directly until write plugins. For simple
* rules control use [[MarkdownIt.disable]], [[MarkdownIt.enable]] and
* [[MarkdownIt.use]].
**/
/**
* new Ruler()
**/
function Ruler() {
	this.__rules__ = [];
	this.__cache__ = null;
}
Ruler.prototype.__find__ = function(name) {
	for (let i = 0; i < this.__rules__.length; i++) if (this.__rules__[i].name === name) return i;
	return -1;
};
Ruler.prototype.__compile__ = function() {
	const self = this;
	const chains = [""];
	self.__rules__.forEach(function(rule) {
		if (!rule.enabled) return;
		rule.alt.forEach(function(altName) {
			if (chains.indexOf(altName) < 0) chains.push(altName);
		});
	});
	self.__cache__ = {};
	chains.forEach(function(chain) {
		self.__cache__[chain] = [];
		self.__rules__.forEach(function(rule) {
			if (!rule.enabled) return;
			if (chain && rule.alt.indexOf(chain) < 0) return;
			self.__cache__[chain].push(rule.fn);
		});
	});
};
/**
* Ruler.at(name, fn [, options])
* - name (String): rule name to replace.
* - fn (Function): new rule function.
* - options (Object): new rule options (not mandatory).
*
* Replace rule by name with new function & options. Throws error if name not
* found.
*
* ##### Options:
*
* - __alt__ - array with names of "alternate" chains.
*
* ##### Example
*
* Replace existing typographer replacement rule with new one:
*
* ```javascript
* var md = require('markdown-it')();
*
* md.core.ruler.at('replacements', function replace(state) {
*   //...
* });
* ```
**/
Ruler.prototype.at = function(name, fn, options) {
	const index = this.__find__(name);
	const opt = options || {};
	if (index === -1) throw new Error("Parser rule not found: " + name);
	this.__rules__[index].fn = fn;
	this.__rules__[index].alt = opt.alt || [];
	this.__cache__ = null;
};
/**
* Ruler.before(beforeName, ruleName, fn [, options])
* - beforeName (String): new rule will be added before this one.
* - ruleName (String): name of added rule.
* - fn (Function): rule function.
* - options (Object): rule options (not mandatory).
*
* Add new rule to chain before one with given name. See also
* [[Ruler.after]], [[Ruler.push]].
*
* ##### Options:
*
* - __alt__ - array with names of "alternate" chains.
*
* ##### Example
*
* ```javascript
* var md = require('markdown-it')();
*
* md.block.ruler.before('paragraph', 'my_rule', function replace(state) {
*   //...
* });
* ```
**/
Ruler.prototype.before = function(beforeName, ruleName, fn, options) {
	const index = this.__find__(beforeName);
	const opt = options || {};
	if (index === -1) throw new Error("Parser rule not found: " + beforeName);
	this.__rules__.splice(index, 0, {
		name: ruleName,
		enabled: true,
		fn,
		alt: opt.alt || []
	});
	this.__cache__ = null;
};
/**
* Ruler.after(afterName, ruleName, fn [, options])
* - afterName (String): new rule will be added after this one.
* - ruleName (String): name of added rule.
* - fn (Function): rule function.
* - options (Object): rule options (not mandatory).
*
* Add new rule to chain after one with given name. See also
* [[Ruler.before]], [[Ruler.push]].
*
* ##### Options:
*
* - __alt__ - array with names of "alternate" chains.
*
* ##### Example
*
* ```javascript
* var md = require('markdown-it')();
*
* md.inline.ruler.after('text', 'my_rule', function replace(state) {
*   //...
* });
* ```
**/
Ruler.prototype.after = function(afterName, ruleName, fn, options) {
	const index = this.__find__(afterName);
	const opt = options || {};
	if (index === -1) throw new Error("Parser rule not found: " + afterName);
	this.__rules__.splice(index + 1, 0, {
		name: ruleName,
		enabled: true,
		fn,
		alt: opt.alt || []
	});
	this.__cache__ = null;
};
/**
* Ruler.push(ruleName, fn [, options])
* - ruleName (String): name of added rule.
* - fn (Function): rule function.
* - options (Object): rule options (not mandatory).
*
* Push new rule to the end of chain. See also
* [[Ruler.before]], [[Ruler.after]].
*
* ##### Options:
*
* - __alt__ - array with names of "alternate" chains.
*
* ##### Example
*
* ```javascript
* var md = require('markdown-it')();
*
* md.core.ruler.push('my_rule', function replace(state) {
*   //...
* });
* ```
**/
Ruler.prototype.push = function(ruleName, fn, options) {
	const opt = options || {};
	this.__rules__.push({
		name: ruleName,
		enabled: true,
		fn,
		alt: opt.alt || []
	});
	this.__cache__ = null;
};
/**
* Ruler.enable(list [, ignoreInvalid]) -> Array
* - list (String|Array): list of rule names to enable.
* - ignoreInvalid (Boolean): set `true` to ignore errors when rule not found.
*
* Enable rules with given names. If any rule name not found - throw Error.
* Errors can be disabled by second param.
*
* Returns list of found rule names (if no exception happened).
*
* See also [[Ruler.disable]], [[Ruler.enableOnly]].
**/
Ruler.prototype.enable = function(list, ignoreInvalid) {
	if (!Array.isArray(list)) list = [list];
	const result = [];
	list.forEach(function(name) {
		const idx = this.__find__(name);
		if (idx < 0) {
			if (ignoreInvalid) return;
			throw new Error("Rules manager: invalid rule name " + name);
		}
		this.__rules__[idx].enabled = true;
		result.push(name);
	}, this);
	this.__cache__ = null;
	return result;
};
/**
* Ruler.enableOnly(list [, ignoreInvalid])
* - list (String|Array): list of rule names to enable (whitelist).
* - ignoreInvalid (Boolean): set `true` to ignore errors when rule not found.
*
* Enable rules with given names, and disable everything else. If any rule name
* not found - throw Error. Errors can be disabled by second param.
*
* See also [[Ruler.disable]], [[Ruler.enable]].
**/
Ruler.prototype.enableOnly = function(list, ignoreInvalid) {
	if (!Array.isArray(list)) list = [list];
	this.__rules__.forEach(function(rule) {
		rule.enabled = false;
	});
	this.enable(list, ignoreInvalid);
};
/**
* Ruler.disable(list [, ignoreInvalid]) -> Array
* - list (String|Array): list of rule names to disable.
* - ignoreInvalid (Boolean): set `true` to ignore errors when rule not found.
*
* Disable rules with given names. If any rule name not found - throw Error.
* Errors can be disabled by second param.
*
* Returns list of found rule names (if no exception happened).
*
* See also [[Ruler.enable]], [[Ruler.enableOnly]].
**/
Ruler.prototype.disable = function(list, ignoreInvalid) {
	if (!Array.isArray(list)) list = [list];
	const result = [];
	list.forEach(function(name) {
		const idx = this.__find__(name);
		if (idx < 0) {
			if (ignoreInvalid) return;
			throw new Error("Rules manager: invalid rule name " + name);
		}
		this.__rules__[idx].enabled = false;
		result.push(name);
	}, this);
	this.__cache__ = null;
	return result;
};
/**
* Ruler.getRules(chainName) -> Array
*
* Return array of active functions (rules) for given chain name. It analyzes
* rules configuration, compiles caches if not exists and returns result.
*
* Default chain name is `''` (empty string). It can't be skipped. That's
* done intentionally, to keep signature monomorphic for high speed.
**/
Ruler.prototype.getRules = function(chainName) {
	if (this.__cache__ === null) this.__compile__();
	return this.__cache__[chainName] || [];
};
//#endregion
//#region node_modules/markdown-it/lib/token.mjs
/**
* class Token
**/
/**
* new Token(type, tag, nesting)
*
* Create new token and fill passed properties.
**/
function Token(type, tag, nesting) {
	/**
	* Token#type -> String
	*
	* Type of the token (string, e.g. "paragraph_open")
	**/
	this.type = type;
	/**
	* Token#tag -> String
	*
	* html tag name, e.g. "p"
	**/
	this.tag = tag;
	/**
	* Token#attrs -> Array
	*
	* Html attributes. Format: `[ [ name1, value1 ], [ name2, value2 ] ]`
	**/
	this.attrs = null;
	/**
	* Token#map -> Array
	*
	* Source map info. Format: `[ line_begin, line_end ]`
	**/
	this.map = null;
	/**
	* Token#nesting -> Number
	*
	* Level change (number in {-1, 0, 1} set), where:
	*
	* -  `1` means the tag is opening
	* -  `0` means the tag is self-closing
	* - `-1` means the tag is closing
	**/
	this.nesting = nesting;
	/**
	* Token#level -> Number
	*
	* nesting level, the same as `state.level`
	**/
	this.level = 0;
	/**
	* Token#children -> Array
	*
	* An array of child nodes (inline and img tokens)
	**/
	this.children = null;
	/**
	* Token#content -> String
	*
	* In a case of self-closing tag (code, html, fence, etc.),
	* it has contents of this tag.
	**/
	this.content = "";
	/**
	* Token#markup -> String
	*
	* '*' or '_' for emphasis, fence string for fence, etc.
	**/
	this.markup = "";
	/**
	* Token#info -> String
	*
	* Additional information:
	*
	* - Info string for "fence" tokens
	* - The value "auto" for autolink "link_open" and "link_close" tokens
	* - The string value of the item marker for ordered-list "list_item_open" tokens
	**/
	this.info = "";
	/**
	* Token#meta -> Object
	*
	* A place for plugins to store an arbitrary data
	**/
	this.meta = null;
	/**
	* Token#block -> Boolean
	*
	* True for block-level tokens, false for inline tokens.
	* Used in renderer to calculate line breaks
	**/
	this.block = false;
	/**
	* Token#hidden -> Boolean
	*
	* If it's true, ignore this element when rendering. Used for tight lists
	* to hide paragraphs.
	**/
	this.hidden = false;
}
/**
* Token.attrIndex(name) -> Number
*
* Search attribute index by name.
**/
Token.prototype.attrIndex = function attrIndex(name) {
	if (!this.attrs) return -1;
	const attrs = this.attrs;
	for (let i = 0, len = attrs.length; i < len; i++) if (attrs[i][0] === name) return i;
	return -1;
};
/**
* Token.attrPush(attrData)
*
* Add `[ name, value ]` attribute to list. Init attrs if necessary
**/
Token.prototype.attrPush = function attrPush(attrData) {
	if (this.attrs) this.attrs.push(attrData);
	else this.attrs = [attrData];
};
/**
* Token.attrSet(name, value)
*
* Set `name` attribute to `value`. Override old value if exists.
**/
Token.prototype.attrSet = function attrSet(name, value) {
	const idx = this.attrIndex(name);
	const attrData = [name, value];
	if (idx < 0) this.attrPush(attrData);
	else this.attrs[idx] = attrData;
};
/**
* Token.attrGet(name)
*
* Get the value of attribute `name`, or null if it does not exist.
**/
Token.prototype.attrGet = function attrGet(name) {
	const idx = this.attrIndex(name);
	let value = null;
	if (idx >= 0) value = this.attrs[idx][1];
	return value;
};
/**
* Token.attrJoin(name, value)
*
* Join value to existing attribute via space. Or create new attribute if not
* exists. Useful to operate with token classes.
**/
Token.prototype.attrJoin = function attrJoin(name, value) {
	const idx = this.attrIndex(name);
	if (idx < 0) this.attrPush([name, value]);
	else this.attrs[idx][1] = this.attrs[idx][1] + " " + value;
};
//#endregion
//#region node_modules/markdown-it/lib/rules_core/state_core.mjs
function StateCore(src, md, env) {
	this.src = src;
	this.env = env;
	this.tokens = [];
	this.inlineMode = false;
	this.md = md;
}
StateCore.prototype.Token = Token;
//#endregion
//#region node_modules/markdown-it/lib/rules_core/normalize.mjs
var NEWLINES_RE = /\r\n?|\n/g;
var NULL_RE = /\0/g;
function normalize(state) {
	let str;
	str = state.src.replace(NEWLINES_RE, "\n");
	str = str.replace(NULL_RE, "�");
	state.src = str;
}
//#endregion
//#region node_modules/markdown-it/lib/rules_core/block.mjs
function block(state) {
	let token;
	if (state.inlineMode) {
		token = new state.Token("inline", "", 0);
		token.content = state.src;
		token.map = [0, 1];
		token.children = [];
		state.tokens.push(token);
	} else state.md.block.parse(state.src, state.md, state.env, state.tokens);
}
//#endregion
//#region node_modules/markdown-it/lib/rules_core/inline.mjs
function inline(state) {
	const tokens = state.tokens;
	for (let i = 0, l = tokens.length; i < l; i++) {
		const tok = tokens[i];
		if (tok.type === "inline") state.md.inline.parse(tok.content, state.md, state.env, tok.children);
	}
}
//#endregion
//#region node_modules/markdown-it/lib/rules_core/linkify.mjs
function isLinkOpen$1(str) {
	return /^<a[>\s]/i.test(str);
}
function isLinkClose$1(str) {
	return /^<\/a\s*>/i.test(str);
}
function linkify$1(state) {
	const blockTokens = state.tokens;
	if (!state.md.options.linkify) return;
	for (let j = 0, l = blockTokens.length; j < l; j++) {
		if (blockTokens[j].type !== "inline" || !state.md.linkify.pretest(blockTokens[j].content)) continue;
		const tokens = blockTokens[j].children;
		const replacements = [];
		let htmlLinkLevel = 0;
		for (let i = tokens.length - 1; i >= 0; i--) {
			const currentToken = tokens[i];
			if (currentToken.type === "link_close") {
				i--;
				while (tokens[i].level !== currentToken.level && tokens[i].type !== "link_open") i--;
				continue;
			}
			if (currentToken.type === "html_inline") {
				if (isLinkOpen$1(currentToken.content) && htmlLinkLevel > 0) htmlLinkLevel--;
				if (isLinkClose$1(currentToken.content)) htmlLinkLevel++;
			}
			if (htmlLinkLevel > 0) continue;
			if (currentToken.type === "text" && state.md.linkify.test(currentToken.content)) {
				const text = currentToken.content;
				let links = state.md.linkify.match(text);
				const nodes = [];
				let level = currentToken.level;
				let lastPos = 0;
				if (links.length > 0 && links[0].index === 0 && i > 0 && tokens[i - 1].type === "text_special") links = links.slice(1);
				for (let ln = 0; ln < links.length; ln++) {
					const url = links[ln].url;
					const fullUrl = state.md.normalizeLink(url);
					if (!state.md.validateLink(fullUrl)) continue;
					let urlText = links[ln].text;
					if (!links[ln].schema) urlText = state.md.normalizeLinkText("http://" + urlText).replace(/^http:\/\//, "");
					else if (links[ln].schema === "mailto:" && !/^mailto:/i.test(urlText)) urlText = state.md.normalizeLinkText("mailto:" + urlText).replace(/^mailto:/, "");
					else urlText = state.md.normalizeLinkText(urlText);
					const pos = links[ln].index;
					if (pos > lastPos) {
						const token = new state.Token("text", "", 0);
						token.content = text.slice(lastPos, pos);
						token.level = level;
						nodes.push(token);
					}
					const token_o = new state.Token("link_open", "a", 1);
					token_o.attrs = [["href", fullUrl]];
					token_o.level = level++;
					token_o.markup = "linkify";
					token_o.info = "auto";
					nodes.push(token_o);
					const token_t = new state.Token("text", "", 0);
					token_t.content = urlText;
					token_t.level = level;
					nodes.push(token_t);
					const token_c = new state.Token("link_close", "a", -1);
					token_c.level = --level;
					token_c.markup = "linkify";
					token_c.info = "auto";
					nodes.push(token_c);
					lastPos = links[ln].lastIndex;
				}
				if (lastPos < text.length) {
					const token = new state.Token("text", "", 0);
					token.content = text.slice(lastPos);
					token.level = level;
					nodes.push(token);
				}
				replacements.push({
					index: i,
					nodes
				});
			}
		}
		if (replacements.length > 0) {
			let newTokensLength = tokens.length;
			for (const replacement of replacements) newTokensLength += replacement.nodes.length - 1;
			const newTokens = new Array(newTokensLength);
			let replacementIndex = 0;
			let newTokenIndex = 0;
			replacements.reverse();
			for (let i = 0; i < tokens.length; i++) {
				const replacement = replacements[replacementIndex];
				if (replacement?.index === i) {
					for (const node of replacement.nodes) newTokens[newTokenIndex++] = node;
					replacementIndex++;
				} else newTokens[newTokenIndex++] = tokens[i];
			}
			blockTokens[j].children = newTokens;
		}
	}
}
//#endregion
//#region node_modules/markdown-it/lib/rules_core/replacements.mjs
var RARE_RE = /\+-|\.\.|\?\?\?\?|!!!!|,,|--/;
var SCOPED_ABBR_TEST_RE = /\((c|tm|r)\)/i;
var SCOPED_ABBR_RE = /\((c|tm|r)\)/gi;
var SCOPED_ABBR = {
	c: "©",
	r: "®",
	tm: "™"
};
function replaceFn(match, name) {
	return SCOPED_ABBR[name.toLowerCase()];
}
function replace_scoped(inlineTokens) {
	let inside_autolink = 0;
	for (let i = inlineTokens.length - 1; i >= 0; i--) {
		const token = inlineTokens[i];
		if (token.type === "text" && !inside_autolink) token.content = token.content.replace(SCOPED_ABBR_RE, replaceFn);
		if (token.type === "link_open" && token.info === "auto") inside_autolink--;
		if (token.type === "link_close" && token.info === "auto") inside_autolink++;
	}
}
function replace_rare(inlineTokens) {
	let inside_autolink = 0;
	for (let i = inlineTokens.length - 1; i >= 0; i--) {
		const token = inlineTokens[i];
		if (token.type === "text" && !inside_autolink) {
			if (RARE_RE.test(token.content)) token.content = token.content.replace(/\+-/g, "±").replace(/\.{2,}/g, "…").replace(/([?!])…/g, "$1..").replace(/([?!]){4,}/g, "$1$1$1").replace(/,{2,}/g, ",").replace(/(^|[^-])---(?=[^-]|$)/gm, "$1—").replace(/(^|\s)--(?=\s|$)/gm, "$1–").replace(/(^|[^-\s])--(?=[^-\s]|$)/gm, "$1–");
		}
		if (token.type === "link_open" && token.info === "auto") inside_autolink--;
		if (token.type === "link_close" && token.info === "auto") inside_autolink++;
	}
}
function replace(state) {
	let blkIdx;
	if (!state.md.options.typographer) return;
	for (blkIdx = state.tokens.length - 1; blkIdx >= 0; blkIdx--) {
		if (state.tokens[blkIdx].type !== "inline") continue;
		if (SCOPED_ABBR_TEST_RE.test(state.tokens[blkIdx].content)) replace_scoped(state.tokens[blkIdx].children);
		if (RARE_RE.test(state.tokens[blkIdx].content)) replace_rare(state.tokens[blkIdx].children);
	}
}
//#endregion
//#region node_modules/markdown-it/lib/rules_core/smartquotes.mjs
var QUOTE_TEST_RE = /['"]/;
var QUOTE_RE = /['"]/g;
var APOSTROPHE = "’";
var MAX_OPENERS = 1e3;
function truncateStack(stack, heads, length) {
	while (stack.length > length) {
		const item = stack.pop();
		if (item.isSingleQuote) heads.single = item.prevSameQuoteIdx;
		else heads.double = item.prevSameQuoteIdx;
	}
}
function addReplacement(replacements, tokenIdx, pos, ch) {
	if (!replacements[tokenIdx]) replacements[tokenIdx] = [];
	replacements[tokenIdx].push({
		pos,
		ch
	});
}
function applyReplacements(str, replacements) {
	let result = "";
	let lastPos = 0;
	replacements.sort((a, b) => a.pos - b.pos);
	for (let i = 0; i < replacements.length; i++) {
		const replacement = replacements[i];
		result += str.slice(lastPos, replacement.pos) + replacement.ch;
		lastPos = replacement.pos + 1;
	}
	return result + str.slice(lastPos);
}
function process_inlines(tokens, state) {
	let j;
	const stack = [];
	const heads = {
		single: -1,
		double: -1
	};
	const replacements = {};
	for (let i = 0; i < tokens.length; i++) {
		const token = tokens[i];
		const thisLevel = tokens[i].level;
		for (j = stack.length - 1; j >= 0; j--) if (stack[j].level <= thisLevel) break;
		truncateStack(stack, heads, j + 1);
		if (token.type !== "text") continue;
		const text = token.content;
		let pos = 0;
		const max = text.length;
		OUTER: while (pos < max) {
			QUOTE_RE.lastIndex = pos;
			const t = QUOTE_RE.exec(text);
			if (!t) break;
			let canOpen = true;
			let canClose = true;
			pos = t.index + 1;
			const isSingle = t[0] === "'";
			let lastChar = 32;
			if (t.index - 1 >= 0) lastChar = text.charCodeAt(t.index - 1);
			else for (j = i - 1; j >= 0; j--) {
				if (tokens[j].type === "softbreak" || tokens[j].type === "hardbreak") break;
				if (!tokens[j].content) continue;
				lastChar = tokens[j].content.charCodeAt(tokens[j].content.length - 1);
				break;
			}
			let nextChar = 32;
			if (pos < max) nextChar = text.charCodeAt(pos);
			else for (j = i + 1; j < tokens.length; j++) {
				if (tokens[j].type === "softbreak" || tokens[j].type === "hardbreak") break;
				if (!tokens[j].content) continue;
				nextChar = tokens[j].content.charCodeAt(0);
				break;
			}
			const isLastPunctChar = isMdAsciiPunct(lastChar) || isPunctCharCode(lastChar);
			const isNextPunctChar = isMdAsciiPunct(nextChar) || isPunctCharCode(nextChar);
			const isLastWhiteSpace = isWhiteSpace(lastChar);
			const isNextWhiteSpace = isWhiteSpace(nextChar);
			if (isNextWhiteSpace) canOpen = false;
			else if (isNextPunctChar) {
				if (!(isLastWhiteSpace || isLastPunctChar)) canOpen = false;
			}
			if (isLastWhiteSpace) canClose = false;
			else if (isLastPunctChar) {
				if (!(isNextWhiteSpace || isNextPunctChar)) canClose = false;
			}
			if (nextChar === 34 && t[0] === "\"") {
				if (lastChar >= 48 && lastChar <= 57) canClose = canOpen = false;
			}
			if (canOpen && canClose) {
				canOpen = isLastPunctChar;
				canClose = isNextPunctChar;
			}
			if (!canOpen && !canClose) {
				if (isSingle) addReplacement(replacements, i, t.index, APOSTROPHE);
				continue;
			}
			if (canClose) {
				j = isSingle ? heads.single : heads.double;
				if (j >= 0 && stack[j].level === thisLevel) {
					const item = stack[j];
					let openQuote;
					let closeQuote;
					if (isSingle) {
						openQuote = state.md.options.quotes[2];
						closeQuote = state.md.options.quotes[3];
					} else {
						openQuote = state.md.options.quotes[0];
						closeQuote = state.md.options.quotes[1];
					}
					addReplacement(replacements, i, t.index, closeQuote);
					addReplacement(replacements, item.tokenIdx, item.contentPos, openQuote);
					truncateStack(stack, heads, j);
					continue OUTER;
				}
			}
			if (canOpen) {
				if (stack.length >= MAX_OPENERS) return;
				stack.push({
					tokenIdx: i,
					contentPos: t.index,
					isSingleQuote: isSingle,
					level: thisLevel,
					prevSameQuoteIdx: isSingle ? heads.single : heads.double
				});
				if (isSingle) heads.single = stack.length - 1;
				else heads.double = stack.length - 1;
			} else if (canClose && isSingle) addReplacement(replacements, i, t.index, APOSTROPHE);
		}
	}
	Object.keys(replacements).forEach(function(tokenIdx) {
		tokens[tokenIdx].content = applyReplacements(tokens[tokenIdx].content, replacements[tokenIdx]);
	});
}
function smartquotes(state) {
	if (!state.md.options.typographer) return;
	for (let blkIdx = state.tokens.length - 1; blkIdx >= 0; blkIdx--) {
		if (state.tokens[blkIdx].type !== "inline" || !QUOTE_TEST_RE.test(state.tokens[blkIdx].content)) continue;
		process_inlines(state.tokens[blkIdx].children, state);
	}
}
//#endregion
//#region node_modules/markdown-it/lib/rules_core/text_join.mjs
function text_join(state) {
	let curr, last;
	const blockTokens = state.tokens;
	const l = blockTokens.length;
	for (let j = 0; j < l; j++) {
		if (blockTokens[j].type !== "inline") continue;
		const tokens = blockTokens[j].children;
		const max = tokens.length;
		for (curr = 0; curr < max; curr++) if (tokens[curr].type === "text_special") tokens[curr].type = "text";
		for (curr = last = 0; curr < max; curr++) if (tokens[curr].type === "text" && curr + 1 < max && tokens[curr + 1].type === "text") tokens[curr + 1].content = tokens[curr].content + tokens[curr + 1].content;
		else {
			if (curr !== last) tokens[last] = tokens[curr];
			last++;
		}
		if (curr !== last) tokens.length = last;
	}
}
//#endregion
//#region node_modules/markdown-it/lib/parser_core.mjs
/** internal
* class Core
*
* Top-level rules executor. Glues block/inline parsers and does intermediate
* transformations.
**/
var _rules$2 = [
	["normalize", normalize],
	["block", block],
	["inline", inline],
	["linkify", linkify$1],
	["replacements", replace],
	["smartquotes", smartquotes],
	["text_join", text_join]
];
/**
* new Core()
**/
function Core() {
	/**
	* Core#ruler -> Ruler
	*
	* [[Ruler]] instance. Keep configuration of core rules.
	**/
	this.ruler = new Ruler();
	for (let i = 0; i < _rules$2.length; i++) this.ruler.push(_rules$2[i][0], _rules$2[i][1]);
}
/**
* Core.process(state)
*
* Executes core chain rules.
**/
Core.prototype.process = function(state) {
	const rules = this.ruler.getRules("");
	for (let i = 0, l = rules.length; i < l; i++) rules[i](state);
};
Core.prototype.State = StateCore;
//#endregion
//#region node_modules/markdown-it/lib/rules_block/state_block.mjs
function StateBlock(src, md, env, tokens) {
	this.src = src;
	this.md = md;
	this.env = env;
	this.tokens = tokens;
	this.bMarks = [];
	this.eMarks = [];
	this.tShift = [];
	this.sCount = [];
	this.bsCount = [];
	this.blkIndent = 0;
	this.line = 0;
	this.lineMax = 0;
	this.tight = false;
	this.ddIndent = -1;
	this.listIndent = -1;
	this.parentType = "root";
	this.level = 0;
	const s = this.src;
	for (let start = 0, pos = 0, indent = 0, offset = 0, len = s.length, indent_found = false; pos < len; pos++) {
		const ch = s.charCodeAt(pos);
		if (!indent_found) if (isSpace(ch)) {
			indent++;
			if (ch === 9) offset += 4 - offset % 4;
			else offset++;
			continue;
		} else indent_found = true;
		if (ch === 10 || pos === len - 1) {
			if (ch !== 10) pos++;
			this.bMarks.push(start);
			this.eMarks.push(pos);
			this.tShift.push(indent);
			this.sCount.push(offset);
			this.bsCount.push(0);
			indent_found = false;
			indent = 0;
			offset = 0;
			start = pos + 1;
		}
	}
	this.bMarks.push(s.length);
	this.eMarks.push(s.length);
	this.tShift.push(0);
	this.sCount.push(0);
	this.bsCount.push(0);
	this.lineMax = this.bMarks.length - 1;
}
StateBlock.prototype.push = function(type, tag, nesting) {
	const token = new Token(type, tag, nesting);
	token.block = true;
	if (nesting < 0) this.level--;
	token.level = this.level;
	if (nesting > 0) this.level++;
	this.tokens.push(token);
	return token;
};
StateBlock.prototype.isEmpty = function isEmpty(line) {
	return this.bMarks[line] + this.tShift[line] >= this.eMarks[line];
};
StateBlock.prototype.skipEmptyLines = function skipEmptyLines(from) {
	for (let max = this.lineMax; from < max; from++) if (this.bMarks[from] + this.tShift[from] < this.eMarks[from]) break;
	return from;
};
StateBlock.prototype.skipSpaces = function skipSpaces(pos) {
	for (let max = this.src.length; pos < max; pos++) if (!isSpace(this.src.charCodeAt(pos))) break;
	return pos;
};
StateBlock.prototype.skipSpacesBack = function skipSpacesBack(pos, min) {
	if (pos <= min) return pos;
	while (pos > min) if (!isSpace(this.src.charCodeAt(--pos))) return pos + 1;
	return pos;
};
StateBlock.prototype.skipChars = function skipChars(pos, code) {
	for (let max = this.src.length; pos < max; pos++) if (this.src.charCodeAt(pos) !== code) break;
	return pos;
};
StateBlock.prototype.skipCharsBack = function skipCharsBack(pos, code, min) {
	if (pos <= min) return pos;
	while (pos > min) if (code !== this.src.charCodeAt(--pos)) return pos + 1;
	return pos;
};
StateBlock.prototype.getLines = function getLines(begin, end, indent, keepLastLF) {
	if (begin >= end) return "";
	const queue = new Array(end - begin);
	for (let i = 0, line = begin; line < end; line++, i++) {
		let lineIndent = 0;
		const lineStart = this.bMarks[line];
		let first = lineStart;
		let last;
		if (line + 1 < end || keepLastLF) last = this.eMarks[line] + 1;
		else last = this.eMarks[line];
		while (first < last && lineIndent < indent) {
			const ch = this.src.charCodeAt(first);
			if (isSpace(ch)) if (ch === 9) lineIndent += 4 - (lineIndent + this.bsCount[line]) % 4;
			else lineIndent++;
			else if (first - lineStart < this.tShift[line]) lineIndent++;
			else break;
			first++;
		}
		if (lineIndent > indent) queue[i] = new Array(lineIndent - indent + 1).join(" ") + this.src.slice(first, last);
		else queue[i] = this.src.slice(first, last);
	}
	return queue.join("");
};
StateBlock.prototype.Token = Token;
//#endregion
//#region node_modules/markdown-it/lib/rules_block/table.mjs
var MAX_AUTOCOMPLETED_CELLS = 65536;
function getLine(state, line) {
	const pos = state.bMarks[line] + state.tShift[line];
	const max = state.eMarks[line];
	return state.src.slice(pos, max);
}
function escapedSplit(str) {
	const result = [];
	const max = str.length;
	let pos = 0;
	let ch = str.charCodeAt(pos);
	let isEscaped = false;
	let lastPos = 0;
	let current = "";
	while (pos < max) {
		if (ch === 124) if (!isEscaped) {
			result.push(current + str.substring(lastPos, pos));
			current = "";
			lastPos = pos + 1;
		} else {
			current += str.substring(lastPos, pos - 1);
			lastPos = pos;
		}
		isEscaped = ch === 92;
		pos++;
		ch = str.charCodeAt(pos);
	}
	result.push(current + str.substring(lastPos));
	return result;
}
function table(state, startLine, endLine, silent) {
	if (startLine + 2 > endLine) return false;
	let nextLine = startLine + 1;
	if (state.sCount[nextLine] < state.blkIndent) return false;
	if (state.sCount[nextLine] - state.blkIndent >= 4) return false;
	let pos = state.bMarks[nextLine] + state.tShift[nextLine];
	if (pos >= state.eMarks[nextLine]) return false;
	const firstCh = state.src.charCodeAt(pos++);
	if (firstCh !== 124 && firstCh !== 45 && firstCh !== 58) return false;
	if (pos >= state.eMarks[nextLine]) return false;
	const secondCh = state.src.charCodeAt(pos++);
	if (secondCh !== 124 && secondCh !== 45 && secondCh !== 58 && !isSpace(secondCh)) return false;
	if (firstCh === 45 && isSpace(secondCh)) return false;
	while (pos < state.eMarks[nextLine]) {
		const ch = state.src.charCodeAt(pos);
		if (ch !== 124 && ch !== 45 && ch !== 58 && !isSpace(ch)) return false;
		pos++;
	}
	let lineText = getLine(state, startLine + 1);
	let columns = lineText.split("|");
	const aligns = [];
	for (let i = 0; i < columns.length; i++) {
		const t = columns[i].trim();
		if (!t) if (i === 0 || i === columns.length - 1) continue;
		else return false;
		if (!/^:?-+:?$/.test(t)) return false;
		if (t.charCodeAt(t.length - 1) === 58) aligns.push(t.charCodeAt(0) === 58 ? "center" : "right");
		else if (t.charCodeAt(0) === 58) aligns.push("left");
		else aligns.push("");
	}
	lineText = getLine(state, startLine).trim();
	if (lineText.indexOf("|") === -1) return false;
	if (state.sCount[startLine] - state.blkIndent >= 4) return false;
	columns = escapedSplit(lineText);
	if (columns.length && columns[0] === "") columns.shift();
	if (columns.length && columns[columns.length - 1] === "") columns.pop();
	const columnCount = columns.length;
	if (columnCount === 0 || columnCount !== aligns.length) return false;
	if (silent) return true;
	const oldParentType = state.parentType;
	state.parentType = "table";
	const terminatorRules = state.md.block.ruler.getRules("blockquote");
	const token_to = state.push("table_open", "table", 1);
	const tableLines = [startLine, 0];
	token_to.map = tableLines;
	const token_tho = state.push("thead_open", "thead", 1);
	token_tho.map = [startLine, startLine + 1];
	const token_htro = state.push("tr_open", "tr", 1);
	token_htro.map = [startLine, startLine + 1];
	for (let i = 0; i < columns.length; i++) {
		const token_ho = state.push("th_open", "th", 1);
		if (aligns[i]) token_ho.attrs = [["style", "text-align:" + aligns[i]]];
		const token_il = state.push("inline", "", 0);
		token_il.content = columns[i].trim();
		token_il.children = [];
		state.push("th_close", "th", -1);
	}
	state.push("tr_close", "tr", -1);
	state.push("thead_close", "thead", -1);
	let tbodyLines;
	let autocompletedCells = 0;
	for (nextLine = startLine + 2; nextLine < endLine; nextLine++) {
		if (state.sCount[nextLine] < state.blkIndent) break;
		let terminate = false;
		for (let i = 0, l = terminatorRules.length; i < l; i++) if (terminatorRules[i](state, nextLine, endLine, true)) {
			terminate = true;
			break;
		}
		if (terminate) break;
		lineText = getLine(state, nextLine).trim();
		if (!lineText) break;
		if (state.sCount[nextLine] - state.blkIndent >= 4) break;
		columns = escapedSplit(lineText);
		if (columns.length && columns[0] === "") columns.shift();
		if (columns.length && columns[columns.length - 1] === "") columns.pop();
		autocompletedCells += columnCount - columns.length;
		if (autocompletedCells > MAX_AUTOCOMPLETED_CELLS) break;
		if (nextLine === startLine + 2) {
			const token_tbo = state.push("tbody_open", "tbody", 1);
			token_tbo.map = tbodyLines = [startLine + 2, 0];
		}
		const token_tro = state.push("tr_open", "tr", 1);
		token_tro.map = [nextLine, nextLine + 1];
		for (let i = 0; i < columnCount; i++) {
			const token_tdo = state.push("td_open", "td", 1);
			if (aligns[i]) token_tdo.attrs = [["style", "text-align:" + aligns[i]]];
			const token_il = state.push("inline", "", 0);
			token_il.content = columns[i] ? columns[i].trim() : "";
			token_il.children = [];
			state.push("td_close", "td", -1);
		}
		state.push("tr_close", "tr", -1);
	}
	if (tbodyLines) {
		state.push("tbody_close", "tbody", -1);
		tbodyLines[1] = nextLine;
	}
	state.push("table_close", "table", -1);
	tableLines[1] = nextLine;
	state.parentType = oldParentType;
	state.line = nextLine;
	return true;
}
//#endregion
//#region node_modules/markdown-it/lib/rules_block/code.mjs
function code(state, startLine, endLine) {
	if (state.sCount[startLine] - state.blkIndent < 4) return false;
	let nextLine = startLine + 1;
	let last = nextLine;
	while (nextLine < endLine) {
		if (state.isEmpty(nextLine)) {
			nextLine++;
			continue;
		}
		if (state.sCount[nextLine] - state.blkIndent >= 4) {
			nextLine++;
			last = nextLine;
			continue;
		}
		break;
	}
	state.line = last;
	const token = state.push("code_block", "code", 0);
	token.content = state.getLines(startLine, last, 4 + state.blkIndent, false) + "\n";
	token.map = [startLine, state.line];
	return true;
}
//#endregion
//#region node_modules/markdown-it/lib/rules_block/fence.mjs
function fence(state, startLine, endLine, silent) {
	let pos = state.bMarks[startLine] + state.tShift[startLine];
	let max = state.eMarks[startLine];
	if (state.sCount[startLine] - state.blkIndent >= 4) return false;
	if (pos + 3 > max) return false;
	const marker = state.src.charCodeAt(pos);
	if (marker !== 126 && marker !== 96) return false;
	let mem = pos;
	pos = state.skipChars(pos, marker);
	let len = pos - mem;
	if (len < 3) return false;
	const markup = state.src.slice(mem, pos);
	const params = state.src.slice(pos, max);
	if (marker === 96) {
		if (params.indexOf(String.fromCharCode(marker)) >= 0) return false;
	}
	if (silent) return true;
	let nextLine = startLine;
	let haveEndMarker = false;
	for (;;) {
		nextLine++;
		if (nextLine >= endLine) break;
		pos = mem = state.bMarks[nextLine] + state.tShift[nextLine];
		max = state.eMarks[nextLine];
		if (pos < max && state.sCount[nextLine] < state.blkIndent) break;
		if (state.src.charCodeAt(pos) !== marker) continue;
		if (state.sCount[nextLine] - state.blkIndent >= 4) continue;
		pos = state.skipChars(pos, marker);
		if (pos - mem < len) continue;
		pos = state.skipSpaces(pos);
		if (pos < max) continue;
		haveEndMarker = true;
		break;
	}
	len = state.sCount[startLine];
	state.line = nextLine + (haveEndMarker ? 1 : 0);
	const token = state.push("fence", "code", 0);
	token.info = params;
	token.content = state.getLines(startLine + 1, nextLine, len, true);
	token.markup = markup;
	token.map = [startLine, state.line];
	return true;
}
//#endregion
//#region node_modules/markdown-it/lib/rules_block/blockquote.mjs
function blockquote(state, startLine, endLine, silent) {
	let pos = state.bMarks[startLine] + state.tShift[startLine];
	let max = state.eMarks[startLine];
	const oldLineMax = state.lineMax;
	if (state.sCount[startLine] - state.blkIndent >= 4) return false;
	if (state.src.charCodeAt(pos) !== 62) return false;
	if (silent) return true;
	const oldBMarks = [];
	const oldBSCount = [];
	const oldSCount = [];
	const oldTShift = [];
	const terminatorRules = state.md.block.ruler.getRules("blockquote");
	const oldParentType = state.parentType;
	state.parentType = "blockquote";
	let lastLineEmpty = false;
	let nextLine;
	for (nextLine = startLine; nextLine < endLine; nextLine++) {
		const isOutdented = state.sCount[nextLine] < state.blkIndent;
		pos = state.bMarks[nextLine] + state.tShift[nextLine];
		max = state.eMarks[nextLine];
		if (pos >= max) break;
		if (state.src.charCodeAt(pos++) === 62 && !isOutdented) {
			let initial = state.sCount[nextLine] + 1;
			let spaceAfterMarker;
			let adjustTab;
			if (state.src.charCodeAt(pos) === 32) {
				pos++;
				initial++;
				adjustTab = false;
				spaceAfterMarker = true;
			} else if (state.src.charCodeAt(pos) === 9) {
				spaceAfterMarker = true;
				if ((state.bsCount[nextLine] + initial) % 4 === 3) {
					pos++;
					initial++;
					adjustTab = false;
				} else adjustTab = true;
			} else spaceAfterMarker = false;
			let offset = initial;
			oldBMarks.push(state.bMarks[nextLine]);
			state.bMarks[nextLine] = pos;
			while (pos < max) {
				const ch = state.src.charCodeAt(pos);
				if (isSpace(ch)) if (ch === 9) offset += 4 - (offset + state.bsCount[nextLine] + (adjustTab ? 1 : 0)) % 4;
				else offset++;
				else break;
				pos++;
			}
			lastLineEmpty = pos >= max;
			oldBSCount.push(state.bsCount[nextLine]);
			state.bsCount[nextLine] = state.sCount[nextLine] + 1 + (spaceAfterMarker ? 1 : 0);
			oldSCount.push(state.sCount[nextLine]);
			state.sCount[nextLine] = offset - initial;
			oldTShift.push(state.tShift[nextLine]);
			state.tShift[nextLine] = pos - state.bMarks[nextLine];
			continue;
		}
		if (lastLineEmpty) break;
		let terminate = false;
		for (let i = 0, l = terminatorRules.length; i < l; i++) if (terminatorRules[i](state, nextLine, endLine, true)) {
			terminate = true;
			break;
		}
		if (terminate) {
			state.lineMax = nextLine;
			if (state.blkIndent !== 0) {
				oldBMarks.push(state.bMarks[nextLine]);
				oldBSCount.push(state.bsCount[nextLine]);
				oldTShift.push(state.tShift[nextLine]);
				oldSCount.push(state.sCount[nextLine]);
				state.sCount[nextLine] -= state.blkIndent;
			}
			break;
		}
		oldBMarks.push(state.bMarks[nextLine]);
		oldBSCount.push(state.bsCount[nextLine]);
		oldTShift.push(state.tShift[nextLine]);
		oldSCount.push(state.sCount[nextLine]);
		state.sCount[nextLine] = -1;
	}
	const oldIndent = state.blkIndent;
	state.blkIndent = 0;
	const token_o = state.push("blockquote_open", "blockquote", 1);
	token_o.markup = ">";
	const lines = [startLine, 0];
	token_o.map = lines;
	state.md.block.tokenize(state, startLine, nextLine);
	const token_c = state.push("blockquote_close", "blockquote", -1);
	token_c.markup = ">";
	state.lineMax = oldLineMax;
	state.parentType = oldParentType;
	lines[1] = state.line;
	for (let i = 0; i < oldTShift.length; i++) {
		state.bMarks[i + startLine] = oldBMarks[i];
		state.tShift[i + startLine] = oldTShift[i];
		state.sCount[i + startLine] = oldSCount[i];
		state.bsCount[i + startLine] = oldBSCount[i];
	}
	state.blkIndent = oldIndent;
	return true;
}
//#endregion
//#region node_modules/markdown-it/lib/rules_block/hr.mjs
function hr(state, startLine, endLine, silent) {
	const max = state.eMarks[startLine];
	if (state.sCount[startLine] - state.blkIndent >= 4) return false;
	let pos = state.bMarks[startLine] + state.tShift[startLine];
	const marker = state.src.charCodeAt(pos++);
	if (marker !== 42 && marker !== 45 && marker !== 95) return false;
	let cnt = 1;
	while (pos < max) {
		const ch = state.src.charCodeAt(pos++);
		if (ch !== marker && !isSpace(ch)) return false;
		if (ch === marker) cnt++;
	}
	if (cnt < 3) return false;
	if (silent) return true;
	state.line = startLine + 1;
	const token = state.push("hr", "hr", 0);
	token.map = [startLine, state.line];
	token.markup = Array(cnt + 1).join(String.fromCharCode(marker));
	return true;
}
//#endregion
//#region node_modules/markdown-it/lib/rules_block/list.mjs
function skipBulletListMarker(state, startLine) {
	const max = state.eMarks[startLine];
	let pos = state.bMarks[startLine] + state.tShift[startLine];
	const marker = state.src.charCodeAt(pos++);
	if (marker !== 42 && marker !== 45 && marker !== 43) return -1;
	if (pos < max) {
		if (!isSpace(state.src.charCodeAt(pos))) return -1;
	}
	return pos;
}
function skipOrderedListMarker(state, startLine) {
	const start = state.bMarks[startLine] + state.tShift[startLine];
	const max = state.eMarks[startLine];
	let pos = start;
	if (pos + 1 >= max) return -1;
	let ch = state.src.charCodeAt(pos++);
	if (ch < 48 || ch > 57) return -1;
	for (;;) {
		if (pos >= max) return -1;
		ch = state.src.charCodeAt(pos++);
		if (ch >= 48 && ch <= 57) {
			if (pos - start >= 10) return -1;
			continue;
		}
		if (ch === 41 || ch === 46) break;
		return -1;
	}
	if (pos < max) {
		ch = state.src.charCodeAt(pos);
		if (!isSpace(ch)) return -1;
	}
	return pos;
}
function markTightParagraphs(state, idx) {
	const level = state.level + 2;
	for (let i = idx + 2, l = state.tokens.length - 2; i < l; i++) if (state.tokens[i].level === level && state.tokens[i].type === "paragraph_open") {
		state.tokens[i + 2].hidden = true;
		state.tokens[i].hidden = true;
		i += 2;
	}
}
function list(state, startLine, endLine, silent) {
	let max, pos, start, token;
	let nextLine = startLine;
	let tight = true;
	if (state.sCount[nextLine] - state.blkIndent >= 4) return false;
	if (state.listIndent >= 0 && state.sCount[nextLine] - state.listIndent >= 4 && state.sCount[nextLine] < state.blkIndent) return false;
	let isTerminatingParagraph = false;
	if (silent && state.parentType === "paragraph") {
		if (state.sCount[nextLine] >= state.blkIndent) isTerminatingParagraph = true;
	}
	let isOrdered;
	let markerValue;
	let posAfterMarker;
	if ((posAfterMarker = skipOrderedListMarker(state, nextLine)) >= 0) {
		isOrdered = true;
		start = state.bMarks[nextLine] + state.tShift[nextLine];
		markerValue = Number(state.src.slice(start, posAfterMarker - 1));
		if (isTerminatingParagraph && markerValue !== 1) return false;
	} else if ((posAfterMarker = skipBulletListMarker(state, nextLine)) >= 0) isOrdered = false;
	else return false;
	if (isTerminatingParagraph) {
		if (state.skipSpaces(posAfterMarker) >= state.eMarks[nextLine]) return false;
	}
	if (silent) return true;
	const markerCharCode = state.src.charCodeAt(posAfterMarker - 1);
	const listTokIdx = state.tokens.length;
	if (isOrdered) {
		token = state.push("ordered_list_open", "ol", 1);
		if (markerValue !== 1) token.attrs = [["start", markerValue]];
	} else token = state.push("bullet_list_open", "ul", 1);
	const listLines = [nextLine, 0];
	token.map = listLines;
	token.markup = String.fromCharCode(markerCharCode);
	let prevEmptyEnd = false;
	const terminatorRules = state.md.block.ruler.getRules("list");
	const oldParentType = state.parentType;
	state.parentType = "list";
	while (nextLine < endLine) {
		pos = posAfterMarker;
		max = state.eMarks[nextLine];
		const initial = state.sCount[nextLine] + posAfterMarker - (state.bMarks[nextLine] + state.tShift[nextLine]);
		let offset = initial;
		while (pos < max) {
			const ch = state.src.charCodeAt(pos);
			if (ch === 9) offset += 4 - (offset + state.bsCount[nextLine]) % 4;
			else if (ch === 32) offset++;
			else break;
			pos++;
		}
		const contentStart = pos;
		let indentAfterMarker;
		if (contentStart >= max) indentAfterMarker = 1;
		else indentAfterMarker = offset - initial;
		if (indentAfterMarker > 4) indentAfterMarker = 1;
		const indent = initial + indentAfterMarker;
		token = state.push("list_item_open", "li", 1);
		token.markup = String.fromCharCode(markerCharCode);
		const itemLines = [nextLine, 0];
		token.map = itemLines;
		if (isOrdered) token.info = state.src.slice(start, posAfterMarker - 1);
		const oldTight = state.tight;
		const oldTShift = state.tShift[nextLine];
		const oldSCount = state.sCount[nextLine];
		const oldListIndent = state.listIndent;
		state.listIndent = state.blkIndent;
		state.blkIndent = indent;
		state.tight = true;
		state.tShift[nextLine] = contentStart - state.bMarks[nextLine];
		state.sCount[nextLine] = offset;
		if (contentStart >= max && state.isEmpty(nextLine + 1)) state.line = Math.min(state.line + 2, endLine);
		else state.md.block.tokenize(state, nextLine, endLine, true);
		if (!state.tight || prevEmptyEnd) tight = false;
		prevEmptyEnd = state.line - nextLine > 1 && state.isEmpty(state.line - 1);
		state.blkIndent = state.listIndent;
		state.listIndent = oldListIndent;
		state.tShift[nextLine] = oldTShift;
		state.sCount[nextLine] = oldSCount;
		state.tight = oldTight;
		token = state.push("list_item_close", "li", -1);
		token.markup = String.fromCharCode(markerCharCode);
		nextLine = state.line;
		itemLines[1] = nextLine;
		if (nextLine >= endLine) break;
		if (state.sCount[nextLine] < state.blkIndent) break;
		if (state.sCount[nextLine] - state.blkIndent >= 4) break;
		let terminate = false;
		for (let i = 0, l = terminatorRules.length; i < l; i++) if (terminatorRules[i](state, nextLine, endLine, true)) {
			terminate = true;
			break;
		}
		if (terminate) break;
		if (isOrdered) {
			posAfterMarker = skipOrderedListMarker(state, nextLine);
			if (posAfterMarker < 0) break;
			start = state.bMarks[nextLine] + state.tShift[nextLine];
		} else {
			posAfterMarker = skipBulletListMarker(state, nextLine);
			if (posAfterMarker < 0) break;
		}
		if (markerCharCode !== state.src.charCodeAt(posAfterMarker - 1)) break;
	}
	if (isOrdered) token = state.push("ordered_list_close", "ol", -1);
	else token = state.push("bullet_list_close", "ul", -1);
	token.markup = String.fromCharCode(markerCharCode);
	listLines[1] = nextLine;
	state.line = nextLine;
	state.parentType = oldParentType;
	if (tight) markTightParagraphs(state, listTokIdx);
	return true;
}
//#endregion
//#region node_modules/markdown-it/lib/rules_block/reference.mjs
function reference(state, startLine, _endLine, silent) {
	let pos = state.bMarks[startLine] + state.tShift[startLine];
	let max = state.eMarks[startLine];
	let nextLine = startLine + 1;
	if (state.sCount[startLine] - state.blkIndent >= 4) return false;
	if (state.src.charCodeAt(pos) !== 91) return false;
	function getNextLine(nextLine) {
		const endLine = state.lineMax;
		if (nextLine >= endLine || state.isEmpty(nextLine)) return null;
		let isContinuation = false;
		if (state.sCount[nextLine] - state.blkIndent > 3) isContinuation = true;
		if (state.sCount[nextLine] < 0) isContinuation = true;
		if (!isContinuation) {
			const terminatorRules = state.md.block.ruler.getRules("reference");
			const oldParentType = state.parentType;
			state.parentType = "reference";
			let terminate = false;
			for (let i = 0, l = terminatorRules.length; i < l; i++) if (terminatorRules[i](state, nextLine, endLine, true)) {
				terminate = true;
				break;
			}
			state.parentType = oldParentType;
			if (terminate) return null;
		}
		const pos = state.bMarks[nextLine] + state.tShift[nextLine];
		const max = state.eMarks[nextLine];
		return state.src.slice(pos, max + 1);
	}
	let str = state.src.slice(pos, max + 1);
	max = str.length;
	let labelEnd = -1;
	for (pos = 1; pos < max; pos++) {
		const ch = str.charCodeAt(pos);
		if (ch === 91) return false;
		else if (ch === 93) {
			labelEnd = pos;
			break;
		} else if (ch === 10) {
			const lineContent = getNextLine(nextLine);
			if (lineContent !== null) {
				str += lineContent;
				max = str.length;
				nextLine++;
			}
		} else if (ch === 92) {
			pos++;
			if (pos < max && str.charCodeAt(pos) === 10) {
				const lineContent = getNextLine(nextLine);
				if (lineContent !== null) {
					str += lineContent;
					max = str.length;
					nextLine++;
				}
			}
		}
	}
	if (labelEnd < 0 || str.charCodeAt(labelEnd + 1) !== 58) return false;
	for (pos = labelEnd + 2; pos < max; pos++) {
		const ch = str.charCodeAt(pos);
		if (ch === 10) {
			const lineContent = getNextLine(nextLine);
			if (lineContent !== null) {
				str += lineContent;
				max = str.length;
				nextLine++;
			}
		} else if (isSpace(ch)) {} else break;
	}
	const destRes = state.md.helpers.parseLinkDestination(str, pos, max);
	if (!destRes.ok) return false;
	const href = state.md.normalizeLink(destRes.str);
	if (!state.md.validateLink(href)) return false;
	pos = destRes.pos;
	const destEndPos = pos;
	const destEndLineNo = nextLine;
	const start = pos;
	for (; pos < max; pos++) {
		const ch = str.charCodeAt(pos);
		if (ch === 10) {
			const lineContent = getNextLine(nextLine);
			if (lineContent !== null) {
				str += lineContent;
				max = str.length;
				nextLine++;
			}
		} else if (isSpace(ch)) {} else break;
	}
	let titleRes = state.md.helpers.parseLinkTitle(str, pos, max);
	while (titleRes.can_continue) {
		const lineContent = getNextLine(nextLine);
		if (lineContent === null) break;
		str += lineContent;
		pos = max;
		max = str.length;
		nextLine++;
		titleRes = state.md.helpers.parseLinkTitle(str, pos, max, titleRes);
	}
	let title;
	if (pos < max && start !== pos && titleRes.ok) {
		title = titleRes.str;
		pos = titleRes.pos;
	} else {
		title = "";
		pos = destEndPos;
		nextLine = destEndLineNo;
	}
	while (pos < max) {
		if (!isSpace(str.charCodeAt(pos))) break;
		pos++;
	}
	if (pos < max && str.charCodeAt(pos) !== 10) {
		if (title) {
			title = "";
			pos = destEndPos;
			nextLine = destEndLineNo;
			while (pos < max) {
				if (!isSpace(str.charCodeAt(pos))) break;
				pos++;
			}
		}
	}
	if (pos < max && str.charCodeAt(pos) !== 10) return false;
	const label = normalizeReference(str.slice(1, labelEnd));
	if (!label) return false;
	/* istanbul ignore if */
	if (silent) return true;
	if (typeof state.env.references === "undefined") state.env.references = {};
	if (typeof state.env.references[label] === "undefined") state.env.references[label] = {
		title,
		href
	};
	state.line = nextLine;
	return true;
}
//#endregion
//#region node_modules/markdown-it/lib/common/html_blocks.mjs
var html_blocks_default = [
	"address",
	"article",
	"aside",
	"base",
	"basefont",
	"blockquote",
	"body",
	"caption",
	"center",
	"col",
	"colgroup",
	"dd",
	"details",
	"dialog",
	"dir",
	"div",
	"dl",
	"dt",
	"fieldset",
	"figcaption",
	"figure",
	"footer",
	"form",
	"frame",
	"frameset",
	"h1",
	"h2",
	"h3",
	"h4",
	"h5",
	"h6",
	"head",
	"header",
	"hr",
	"html",
	"iframe",
	"legend",
	"li",
	"link",
	"main",
	"menu",
	"menuitem",
	"nav",
	"noframes",
	"ol",
	"optgroup",
	"option",
	"p",
	"param",
	"search",
	"section",
	"summary",
	"table",
	"tbody",
	"td",
	"tfoot",
	"th",
	"thead",
	"title",
	"tr",
	"track",
	"ul"
];
//#endregion
//#region node_modules/markdown-it/lib/common/html_re.mjs
var HTML_TAG_RE = /* @__PURE__ */ new RegExp("^(?:<[A-Za-z][A-Za-z0-9\\-]*(?:\\s+[a-zA-Z_:][a-zA-Z0-9:._-]*(?:\\s*=\\s*(?:[^\"'=<>`\\x00-\\x20]+|'[^']*'|\"[^\"]*\"))?)*\\s*\\/?>|<\\/[A-Za-z][A-Za-z0-9\\-]*\\s*>|<!---?>|<!--(?:[^-]|-[^-]|--[^>])*-->|<[?][\\s\\S]*?[?]>|<![A-Za-z][^>]*>|<!\\[CDATA\\[[\\s\\S]*?\\]\\]>)");
var HTML_OPEN_CLOSE_TAG_RE = /* @__PURE__ */ new RegExp("^(?:<[A-Za-z][A-Za-z0-9\\-]*(?:\\s+[a-zA-Z_:][a-zA-Z0-9:._-]*(?:\\s*=\\s*(?:[^\"'=<>`\\x00-\\x20]+|'[^']*'|\"[^\"]*\"))?)*\\s*\\/?>|<\\/[A-Za-z][A-Za-z0-9\\-]*\\s*>)");
//#endregion
//#region node_modules/markdown-it/lib/rules_block/html_block.mjs
var HTML_SEQUENCES = [
	[
		/^<(script|pre|style|textarea)(?=(\s|>|$))/i,
		/<\/(script|pre|style|textarea)>/i,
		true
	],
	[
		/^<!--/,
		/-->/,
		true
	],
	[
		/^<\?/,
		/\?>/,
		true
	],
	[
		/^<![A-Za-z]/,
		/>/,
		true
	],
	[
		/^<!\[CDATA\[/,
		/\]\]>/,
		true
	],
	[
		new RegExp("^</?(" + html_blocks_default.join("|") + ")(?=(\\s|/?>|$))", "i"),
		/^$/,
		true
	],
	[
		new RegExp(HTML_OPEN_CLOSE_TAG_RE.source + "\\s*$"),
		/^$/,
		false
	]
];
function html_block(state, startLine, endLine, silent) {
	let pos = state.bMarks[startLine] + state.tShift[startLine];
	let max = state.eMarks[startLine];
	if (state.sCount[startLine] - state.blkIndent >= 4) return false;
	if (!state.md.options.html) return false;
	if (state.src.charCodeAt(pos) !== 60) return false;
	let lineText = state.src.slice(pos, max);
	let i = 0;
	for (; i < HTML_SEQUENCES.length; i++) if (HTML_SEQUENCES[i][0].test(lineText)) break;
	if (i === HTML_SEQUENCES.length) return false;
	if (silent) return HTML_SEQUENCES[i][2];
	let nextLine = startLine + 1;
	const endsOnBlankLine = HTML_SEQUENCES[i][1].test("");
	if (!HTML_SEQUENCES[i][1].test(lineText)) for (; nextLine < endLine; nextLine++) {
		if (state.sCount[nextLine] < state.blkIndent) {
			if (endsOnBlankLine || !state.isEmpty(nextLine)) break;
		}
		pos = state.bMarks[nextLine] + state.tShift[nextLine];
		max = state.eMarks[nextLine];
		lineText = state.src.slice(pos, max);
		if (HTML_SEQUENCES[i][1].test(lineText)) {
			if (lineText.length !== 0) nextLine++;
			break;
		}
	}
	state.line = nextLine;
	const token = state.push("html_block", "", 0);
	token.map = [startLine, nextLine];
	token.content = state.getLines(startLine, nextLine, state.blkIndent, true);
	return true;
}
//#endregion
//#region node_modules/markdown-it/lib/rules_block/heading.mjs
function heading(state, startLine, endLine, silent) {
	let pos = state.bMarks[startLine] + state.tShift[startLine];
	let max = state.eMarks[startLine];
	if (state.sCount[startLine] - state.blkIndent >= 4) return false;
	let ch = state.src.charCodeAt(pos);
	if (ch !== 35 || pos >= max) return false;
	let level = 1;
	ch = state.src.charCodeAt(++pos);
	while (ch === 35 && pos < max && level <= 6) {
		level++;
		ch = state.src.charCodeAt(++pos);
	}
	if (level > 6 || pos < max && !isSpace(ch)) return false;
	if (silent) return true;
	max = state.skipSpacesBack(max, pos);
	const tmp = state.skipCharsBack(max, 35, pos);
	if (tmp > pos && isSpace(state.src.charCodeAt(tmp - 1))) max = tmp;
	state.line = startLine + 1;
	const token_o = state.push("heading_open", "h" + String(level), 1);
	token_o.markup = "########".slice(0, level);
	token_o.map = [startLine, state.line];
	const token_i = state.push("inline", "", 0);
	token_i.content = asciiTrim(state.src.slice(pos, max));
	token_i.map = [startLine, state.line];
	token_i.children = [];
	const token_c = state.push("heading_close", "h" + String(level), -1);
	token_c.markup = "########".slice(0, level);
	return true;
}
//#endregion
//#region node_modules/markdown-it/lib/rules_block/lheading.mjs
function lheading(state, startLine, endLine) {
	const terminatorRules = state.md.block.ruler.getRules("paragraph");
	if (state.sCount[startLine] - state.blkIndent >= 4) return false;
	const oldParentType = state.parentType;
	state.parentType = "paragraph";
	let level = 0;
	let marker;
	let nextLine = startLine + 1;
	for (; nextLine < endLine && !state.isEmpty(nextLine); nextLine++) {
		if (state.sCount[nextLine] - state.blkIndent > 3) continue;
		if (state.sCount[nextLine] >= state.blkIndent) {
			let pos = state.bMarks[nextLine] + state.tShift[nextLine];
			const max = state.eMarks[nextLine];
			if (pos < max) {
				marker = state.src.charCodeAt(pos);
				if (marker === 45 || marker === 61) {
					pos = state.skipChars(pos, marker);
					pos = state.skipSpaces(pos);
					if (pos >= max) {
						level = marker === 61 ? 1 : 2;
						break;
					}
				}
			}
		}
		if (state.sCount[nextLine] < 0) continue;
		let terminate = false;
		for (let i = 0, l = terminatorRules.length; i < l; i++) if (terminatorRules[i](state, nextLine, endLine, true)) {
			terminate = true;
			break;
		}
		if (terminate) break;
	}
	if (!level) {
		state.parentType = oldParentType;
		return false;
	}
	const content = asciiTrim(state.getLines(startLine, nextLine, state.blkIndent, false));
	state.line = nextLine + 1;
	const token_o = state.push("heading_open", "h" + String(level), 1);
	token_o.markup = String.fromCharCode(marker);
	token_o.map = [startLine, state.line];
	const token_i = state.push("inline", "", 0);
	token_i.content = content;
	token_i.map = [startLine, state.line - 1];
	token_i.children = [];
	const token_c = state.push("heading_close", "h" + String(level), -1);
	token_c.markup = String.fromCharCode(marker);
	state.parentType = oldParentType;
	return true;
}
//#endregion
//#region node_modules/markdown-it/lib/rules_block/paragraph.mjs
function paragraph(state, startLine, endLine) {
	const terminatorRules = state.md.block.ruler.getRules("paragraph");
	const oldParentType = state.parentType;
	let nextLine = startLine + 1;
	state.parentType = "paragraph";
	for (; nextLine < endLine && !state.isEmpty(nextLine); nextLine++) {
		if (state.sCount[nextLine] - state.blkIndent > 3) continue;
		if (state.sCount[nextLine] < 0) continue;
		let terminate = false;
		for (let i = 0, l = terminatorRules.length; i < l; i++) if (terminatorRules[i](state, nextLine, endLine, true)) {
			terminate = true;
			break;
		}
		if (terminate) break;
	}
	const content = asciiTrim(state.getLines(startLine, nextLine, state.blkIndent, false));
	state.line = nextLine;
	const token_o = state.push("paragraph_open", "p", 1);
	token_o.map = [startLine, state.line];
	const token_i = state.push("inline", "", 0);
	token_i.content = content;
	token_i.map = [startLine, state.line];
	token_i.children = [];
	state.push("paragraph_close", "p", -1);
	state.parentType = oldParentType;
	return true;
}
//#endregion
//#region node_modules/markdown-it/lib/parser_block.mjs
/** internal
* class ParserBlock
*
* Block-level tokenizer.
**/
var _rules$1 = [
	[
		"table",
		table,
		["paragraph", "reference"]
	],
	["code", code],
	[
		"fence",
		fence,
		[
			"paragraph",
			"reference",
			"blockquote",
			"list"
		]
	],
	[
		"blockquote",
		blockquote,
		[
			"paragraph",
			"reference",
			"blockquote",
			"list"
		]
	],
	[
		"hr",
		hr,
		[
			"paragraph",
			"reference",
			"blockquote",
			"list"
		]
	],
	[
		"list",
		list,
		[
			"paragraph",
			"reference",
			"blockquote"
		]
	],
	["reference", reference],
	[
		"html_block",
		html_block,
		[
			"paragraph",
			"reference",
			"blockquote"
		]
	],
	[
		"heading",
		heading,
		[
			"paragraph",
			"reference",
			"blockquote"
		]
	],
	["lheading", lheading],
	["paragraph", paragraph]
];
/**
* new ParserBlock()
**/
function ParserBlock() {
	/**
	* ParserBlock#ruler -> Ruler
	*
	* [[Ruler]] instance. Keep configuration of block rules.
	**/
	this.ruler = new Ruler();
	for (let i = 0; i < _rules$1.length; i++) this.ruler.push(_rules$1[i][0], _rules$1[i][1], { alt: (_rules$1[i][2] || []).slice() });
}
ParserBlock.prototype.tokenize = function(state, startLine, endLine) {
	const rules = this.ruler.getRules("");
	const len = rules.length;
	const maxNesting = state.md.options.maxNesting;
	let line = startLine;
	let hasEmptyLines = false;
	while (line < endLine) {
		state.line = line = state.skipEmptyLines(line);
		if (line >= endLine) break;
		if (state.sCount[line] < state.blkIndent) break;
		if (state.level >= maxNesting) {
			state.line = endLine;
			break;
		}
		const prevLine = state.line;
		let ok = false;
		for (let i = 0; i < len; i++) {
			ok = rules[i](state, line, endLine, false);
			if (ok) {
				if (prevLine >= state.line) throw new Error("block rule didn't increment state.line");
				break;
			}
		}
		if (!ok) throw new Error("none of the block rules matched");
		state.tight = !hasEmptyLines;
		if (state.isEmpty(state.line - 1)) hasEmptyLines = true;
		line = state.line;
		if (line < endLine && state.isEmpty(line)) {
			hasEmptyLines = true;
			line++;
			state.line = line;
		}
	}
};
/**
* ParserBlock.parse(str, md, env, outTokens)
*
* Process input string and push block tokens into `outTokens`
**/
ParserBlock.prototype.parse = function(src, md, env, outTokens) {
	if (!src) return;
	const state = new this.State(src, md, env, outTokens);
	this.tokenize(state, state.line, state.lineMax);
};
ParserBlock.prototype.State = StateBlock;
//#endregion
//#region node_modules/markdown-it/lib/rules_inline/state_inline.mjs
function StateInline(src, md, env, outTokens) {
	this.src = src;
	this.env = env;
	this.md = md;
	this.tokens = outTokens;
	this.tokens_meta = Array(outTokens.length);
	this.pos = 0;
	this.posMax = this.src.length;
	this.level = 0;
	this.pending = "";
	this.pendingLevel = 0;
	this.cache = {};
	this.delimiters = [];
	this._prev_delimiters = [];
	this.backticks = {};
	this.backticksScanned = false;
	this.linkLevel = 0;
}
StateInline.prototype.pushPending = function() {
	const token = new Token("text", "", 0);
	token.content = this.pending;
	token.level = this.pendingLevel;
	this.tokens.push(token);
	this.pending = "";
	return token;
};
StateInline.prototype.push = function(type, tag, nesting) {
	if (this.pending) this.pushPending();
	const token = new Token(type, tag, nesting);
	let token_meta = null;
	if (nesting < 0) {
		this.level--;
		this.delimiters = this._prev_delimiters.pop();
	}
	token.level = this.level;
	if (nesting > 0) {
		this.level++;
		this._prev_delimiters.push(this.delimiters);
		this.delimiters = [];
		token_meta = { delimiters: this.delimiters };
	}
	this.pendingLevel = this.level;
	this.tokens.push(token);
	this.tokens_meta.push(token_meta);
	return token;
};
StateInline.prototype.scanDelims = function(start, canSplitWord) {
	const max = this.posMax;
	const marker = this.src.charCodeAt(start);
	let lastChar;
	if (start === 0) lastChar = 32;
	else if (start === 1) {
		lastChar = this.src.charCodeAt(0);
		if ((lastChar & 63488) === 55296) lastChar = 65533;
	} else {
		lastChar = this.src.charCodeAt(start - 1);
		if ((lastChar & 64512) === 56320) {
			const highSurr = this.src.charCodeAt(start - 2);
			lastChar = (highSurr & 64512) === 55296 ? 65536 + (highSurr - 55296 << 10) + (lastChar - 56320) : 65533;
		} else if ((lastChar & 64512) === 55296) lastChar = 65533;
	}
	let pos = start;
	while (pos < max && this.src.charCodeAt(pos) === marker) pos++;
	const count = pos - start;
	let nextChar = pos < max ? this.src.charCodeAt(pos) : 32;
	if ((nextChar & 64512) === 55296) {
		const lowSurr = this.src.charCodeAt(pos + 1);
		nextChar = (lowSurr & 64512) === 56320 ? 65536 + (nextChar - 55296 << 10) + (lowSurr - 56320) : 65533;
	} else if ((nextChar & 64512) === 56320) nextChar = 65533;
	const isLastPunctChar = isMdAsciiPunct(lastChar) || isPunctCharCode(lastChar);
	const isNextPunctChar = isMdAsciiPunct(nextChar) || isPunctCharCode(nextChar);
	const isLastWhiteSpace = isWhiteSpace(lastChar);
	const isNextWhiteSpace = isWhiteSpace(nextChar);
	const left_flanking = !isNextWhiteSpace && (!isNextPunctChar || isLastWhiteSpace || isLastPunctChar);
	const right_flanking = !isLastWhiteSpace && (!isLastPunctChar || isNextWhiteSpace || isNextPunctChar);
	return {
		can_open: left_flanking && (canSplitWord || !right_flanking || isLastPunctChar),
		can_close: right_flanking && (canSplitWord || !left_flanking || isNextPunctChar),
		length: count
	};
};
StateInline.prototype.Token = Token;
//#endregion
//#region node_modules/markdown-it/lib/rules_inline/text.mjs
function isTerminatorChar(ch) {
	switch (ch) {
		case 10:
		case 33:
		case 35:
		case 36:
		case 37:
		case 38:
		case 42:
		case 43:
		case 45:
		case 58:
		case 60:
		case 61:
		case 62:
		case 64:
		case 91:
		case 92:
		case 93:
		case 94:
		case 95:
		case 96:
		case 123:
		case 125:
		case 126: return true;
		default: return false;
	}
}
function text(state, silent) {
	let pos = state.pos;
	while (pos < state.posMax && !isTerminatorChar(state.src.charCodeAt(pos))) pos++;
	if (pos === state.pos) return false;
	if (!silent) state.pending += state.src.slice(state.pos, pos);
	state.pos = pos;
	return true;
}
//#endregion
//#region node_modules/markdown-it/lib/rules_inline/linkify.mjs
function isAsciiAlpha(code) {
	return code >= 65 && code <= 90 || code >= 97 && code <= 122;
}
function isSchemeChar(code) {
	return code >= 65 && code <= 90 || code >= 97 && code <= 122 || code >= 48 && code <= 57 || code === 43 || code === 45 || code === 46;
}
function linkify(state, silent) {
	if (!state.md.options.linkify) return false;
	if (state.linkLevel > 0) return false;
	const pos = state.pos;
	const max = state.posMax;
	if (pos + 3 > max) return false;
	if (state.src.charCodeAt(pos) !== 58) return false;
	if (state.src.charCodeAt(pos + 1) !== 47) return false;
	if (state.src.charCodeAt(pos + 2) !== 47) return false;
	const protoMin = pos - Math.min(10, state.pending.length, pos);
	let protoStart = pos;
	while (protoStart > protoMin && isSchemeChar(state.src.charCodeAt(protoStart - 1))) protoStart--;
	if (protoStart === pos || !isAsciiAlpha(state.src.charCodeAt(protoStart))) return false;
	const protoLength = pos - protoStart;
	const link = state.md.linkify.matchAtStart(state.src.slice(protoStart));
	if (!link) return false;
	let url = link.url;
	if (url.length <= protoLength) return false;
	let urlEnd = url.length;
	while (urlEnd > 0 && url.charCodeAt(urlEnd - 1) === 42) urlEnd--;
	if (urlEnd !== url.length) url = url.slice(0, urlEnd);
	const fullUrl = state.md.normalizeLink(url);
	if (!state.md.validateLink(fullUrl)) return false;
	if (!silent) {
		state.pending = state.pending.slice(0, -protoLength);
		const token_o = state.push("link_open", "a", 1);
		token_o.attrs = [["href", fullUrl]];
		token_o.markup = "linkify";
		token_o.info = "auto";
		const token_t = state.push("text", "", 0);
		token_t.content = state.md.normalizeLinkText(url);
		const token_c = state.push("link_close", "a", -1);
		token_c.markup = "linkify";
		token_c.info = "auto";
	}
	state.pos += url.length - protoLength;
	return true;
}
//#endregion
//#region node_modules/markdown-it/lib/rules_inline/newline.mjs
function newline(state, silent) {
	let pos = state.pos;
	if (state.src.charCodeAt(pos) !== 10) return false;
	const pmax = state.pending.length - 1;
	const max = state.posMax;
	if (!silent) if (pmax >= 0 && state.pending.charCodeAt(pmax) === 32) if (pmax >= 1 && state.pending.charCodeAt(pmax - 1) === 32) {
		let ws = pmax - 1;
		while (ws >= 1 && state.pending.charCodeAt(ws - 1) === 32) ws--;
		state.pending = state.pending.slice(0, ws);
		state.push("hardbreak", "br", 0);
	} else {
		state.pending = state.pending.slice(0, -1);
		state.push("softbreak", "br", 0);
	}
	else state.push("softbreak", "br", 0);
	pos++;
	while (pos < max && isSpace(state.src.charCodeAt(pos))) pos++;
	state.pos = pos;
	return true;
}
//#endregion
//#region node_modules/markdown-it/lib/rules_inline/escape.mjs
var ESCAPED = [];
for (let i = 0; i < 256; i++) ESCAPED.push(0);
"\\!\"#$%&'()*+,./:;<=>?@[]^_`{|}~-".split("").forEach(function(ch) {
	ESCAPED[ch.charCodeAt(0)] = 1;
});
function escape(state, silent) {
	let pos = state.pos;
	const max = state.posMax;
	if (state.src.charCodeAt(pos) !== 92) return false;
	pos++;
	if (pos >= max) return false;
	let ch1 = state.src.charCodeAt(pos);
	if (ch1 === 10) {
		if (!silent) state.push("hardbreak", "br", 0);
		pos++;
		while (pos < max) {
			ch1 = state.src.charCodeAt(pos);
			if (!isSpace(ch1)) break;
			pos++;
		}
		state.pos = pos;
		return true;
	}
	if (ch1 === 32) {
		if (!silent) {
			const token = state.push("text_special", "", 0);
			token.content = "\\";
			token.markup = "\\";
			token.info = "escape";
		}
		state.pos = pos;
		return true;
	}
	let escapedStr = state.src[pos];
	if (ch1 >= 55296 && ch1 <= 56319 && pos + 1 < max) {
		const ch2 = state.src.charCodeAt(pos + 1);
		if (ch2 >= 56320 && ch2 <= 57343) {
			escapedStr += state.src[pos + 1];
			pos++;
		}
	}
	const origStr = "\\" + escapedStr;
	if (!silent) {
		const token = state.push("text_special", "", 0);
		if (ch1 < 256 && ESCAPED[ch1] !== 0) token.content = escapedStr;
		else token.content = origStr;
		token.markup = origStr;
		token.info = "escape";
	}
	state.pos = pos + 1;
	return true;
}
//#endregion
//#region node_modules/markdown-it/lib/rules_inline/backticks.mjs
function backtick(state, silent) {
	let pos = state.pos;
	if (state.src.charCodeAt(pos) !== 96) return false;
	const start = pos;
	pos++;
	const max = state.posMax;
	while (pos < max && state.src.charCodeAt(pos) === 96) pos++;
	const marker = state.src.slice(start, pos);
	const openerLength = marker.length;
	if (state.backticksScanned && (state.backticks[openerLength] || 0) <= start) {
		if (!silent) state.pending += marker;
		state.pos += openerLength;
		return true;
	}
	let matchEnd = pos;
	let matchStart;
	while ((matchStart = state.src.indexOf("`", matchEnd)) !== -1) {
		matchEnd = matchStart + 1;
		while (matchEnd < max && state.src.charCodeAt(matchEnd) === 96) matchEnd++;
		const closerLength = matchEnd - matchStart;
		if (closerLength === openerLength) {
			if (!silent) {
				const token = state.push("code_inline", "code", 0);
				token.markup = marker;
				token.content = state.src.slice(pos, matchStart).replace(/\n/g, " ").replace(/^ (.+) $/, "$1");
			}
			state.pos = matchEnd;
			return true;
		}
		state.backticks[closerLength] = matchStart;
	}
	state.backticksScanned = true;
	if (!silent) state.pending += marker;
	state.pos += openerLength;
	return true;
}
//#endregion
//#region node_modules/markdown-it/lib/rules_inline/strikethrough.mjs
function strikethrough_tokenize(state, silent) {
	const start = state.pos;
	const marker = state.src.charCodeAt(start);
	if (silent) return false;
	if (marker !== 126) return false;
	const scanned = state.scanDelims(state.pos, true);
	let len = scanned.length;
	const ch = String.fromCharCode(marker);
	if (len < 2) return false;
	let token;
	if (len % 2) {
		token = state.push("text", "", 0);
		token.content = ch;
		len--;
	}
	for (let i = 0; i < len; i += 2) {
		token = state.push("text", "", 0);
		token.content = ch + ch;
		state.delimiters.push({
			marker,
			length: 0,
			token: state.tokens.length - 1,
			end: -1,
			open: scanned.can_open,
			close: scanned.can_close
		});
	}
	state.pos += scanned.length;
	return true;
}
function postProcess$1(state, delimiters) {
	let token;
	const loneMarkers = [];
	const max = delimiters.length;
	for (let i = 0; i < max; i++) {
		const startDelim = delimiters[i];
		if (startDelim.marker !== 126) continue;
		if (startDelim.end === -1) continue;
		const endDelim = delimiters[startDelim.end];
		token = state.tokens[startDelim.token];
		token.type = "s_open";
		token.tag = "s";
		token.nesting = 1;
		token.markup = "~~";
		token.content = "";
		token = state.tokens[endDelim.token];
		token.type = "s_close";
		token.tag = "s";
		token.nesting = -1;
		token.markup = "~~";
		token.content = "";
		if (state.tokens[endDelim.token - 1].type === "text" && state.tokens[endDelim.token - 1].content === "~") loneMarkers.push(endDelim.token - 1);
	}
	while (loneMarkers.length) {
		const i = loneMarkers.pop();
		let j = i + 1;
		while (j < state.tokens.length && state.tokens[j].type === "s_close") j++;
		j--;
		if (i !== j) {
			token = state.tokens[j];
			state.tokens[j] = state.tokens[i];
			state.tokens[i] = token;
		}
	}
}
function strikethrough_postProcess(state) {
	const tokens_meta = state.tokens_meta;
	const max = state.tokens_meta.length;
	postProcess$1(state, state.delimiters);
	for (let curr = 0; curr < max; curr++) if (tokens_meta[curr] && tokens_meta[curr].delimiters) postProcess$1(state, tokens_meta[curr].delimiters);
}
var strikethrough_default = {
	tokenize: strikethrough_tokenize,
	postProcess: strikethrough_postProcess
};
//#endregion
//#region node_modules/markdown-it/lib/rules_inline/emphasis.mjs
function emphasis_tokenize(state, silent) {
	const start = state.pos;
	const marker = state.src.charCodeAt(start);
	if (silent) return false;
	if (marker !== 95 && marker !== 42) return false;
	const scanned = state.scanDelims(state.pos, marker === 42);
	for (let i = 0; i < scanned.length; i++) {
		const token = state.push("text", "", 0);
		token.content = String.fromCharCode(marker);
		state.delimiters.push({
			marker,
			length: scanned.length,
			token: state.tokens.length - 1,
			end: -1,
			open: scanned.can_open,
			close: scanned.can_close
		});
	}
	state.pos += scanned.length;
	return true;
}
function postProcess(state, delimiters) {
	const max = delimiters.length;
	for (let i = max - 1; i >= 0; i--) {
		const startDelim = delimiters[i];
		if (startDelim.marker !== 95 && startDelim.marker !== 42) continue;
		if (startDelim.end === -1) continue;
		const endDelim = delimiters[startDelim.end];
		const isStrong = i > 0 && delimiters[i - 1].end === startDelim.end + 1 && delimiters[i - 1].marker === startDelim.marker && delimiters[i - 1].token === startDelim.token - 1 && delimiters[startDelim.end + 1].token === endDelim.token + 1;
		const ch = String.fromCharCode(startDelim.marker);
		const token_o = state.tokens[startDelim.token];
		token_o.type = isStrong ? "strong_open" : "em_open";
		token_o.tag = isStrong ? "strong" : "em";
		token_o.nesting = 1;
		token_o.markup = isStrong ? ch + ch : ch;
		token_o.content = "";
		const token_c = state.tokens[endDelim.token];
		token_c.type = isStrong ? "strong_close" : "em_close";
		token_c.tag = isStrong ? "strong" : "em";
		token_c.nesting = -1;
		token_c.markup = isStrong ? ch + ch : ch;
		token_c.content = "";
		if (isStrong) {
			state.tokens[delimiters[i - 1].token].content = "";
			state.tokens[delimiters[startDelim.end + 1].token].content = "";
			i--;
		}
	}
}
function emphasis_post_process(state) {
	const tokens_meta = state.tokens_meta;
	const max = state.tokens_meta.length;
	postProcess(state, state.delimiters);
	for (let curr = 0; curr < max; curr++) if (tokens_meta[curr] && tokens_meta[curr].delimiters) postProcess(state, tokens_meta[curr].delimiters);
}
var emphasis_default = {
	tokenize: emphasis_tokenize,
	postProcess: emphasis_post_process
};
//#endregion
//#region node_modules/markdown-it/lib/rules_inline/link.mjs
function link(state, silent) {
	let code, label, res, ref;
	let href = "";
	let title = "";
	let start = state.pos;
	let parseReference = true;
	if (state.src.charCodeAt(state.pos) !== 91) return false;
	const oldPos = state.pos;
	const max = state.posMax;
	const labelStart = state.pos + 1;
	const labelEnd = state.md.helpers.parseLinkLabel(state, state.pos, true);
	if (labelEnd < 0) return false;
	let pos = labelEnd + 1;
	if (pos < max && state.src.charCodeAt(pos) === 40) {
		parseReference = false;
		pos++;
		for (; pos < max; pos++) {
			code = state.src.charCodeAt(pos);
			if (!isSpace(code) && code !== 10) break;
		}
		if (pos >= max) return false;
		start = pos;
		res = state.md.helpers.parseLinkDestination(state.src, pos, state.posMax);
		if (res.ok) {
			href = state.md.normalizeLink(res.str);
			if (state.md.validateLink(href)) pos = res.pos;
			else href = "";
			start = pos;
			for (; pos < max; pos++) {
				code = state.src.charCodeAt(pos);
				if (!isSpace(code) && code !== 10) break;
			}
			res = state.md.helpers.parseLinkTitle(state.src, pos, state.posMax);
			if (pos < max && start !== pos && res.ok) {
				title = res.str;
				pos = res.pos;
				for (; pos < max; pos++) {
					code = state.src.charCodeAt(pos);
					if (!isSpace(code) && code !== 10) break;
				}
			}
		}
		if (pos >= max || state.src.charCodeAt(pos) !== 41) parseReference = true;
		pos++;
	}
	if (parseReference) {
		if (typeof state.env.references === "undefined") return false;
		if (pos < max && state.src.charCodeAt(pos) === 91) {
			start = pos + 1;
			pos = state.md.helpers.parseLinkLabel(state, pos);
			if (pos >= 0) label = state.src.slice(start, pos++);
			else pos = labelEnd + 1;
		} else pos = labelEnd + 1;
		if (!label) label = state.src.slice(labelStart, labelEnd);
		ref = state.env.references[normalizeReference(label)];
		if (!ref) {
			state.pos = oldPos;
			return false;
		}
		href = ref.href;
		title = ref.title;
	}
	if (!silent) {
		state.pos = labelStart;
		state.posMax = labelEnd;
		const token_o = state.push("link_open", "a", 1);
		const attrs = [["href", href]];
		token_o.attrs = attrs;
		if (title) attrs.push(["title", title]);
		state.linkLevel++;
		state.md.inline.tokenize(state);
		state.linkLevel--;
		state.push("link_close", "a", -1);
	}
	state.pos = pos;
	state.posMax = max;
	return true;
}
//#endregion
//#region node_modules/markdown-it/lib/rules_inline/image.mjs
function image(state, silent) {
	let code, content, label, pos, ref, res, title, start;
	let href = "";
	const oldPos = state.pos;
	const max = state.posMax;
	if (state.src.charCodeAt(state.pos) !== 33) return false;
	if (state.src.charCodeAt(state.pos + 1) !== 91) return false;
	const labelStart = state.pos + 2;
	const labelEnd = state.md.helpers.parseLinkLabel(state, state.pos + 1, false);
	if (labelEnd < 0) return false;
	pos = labelEnd + 1;
	if (pos < max && state.src.charCodeAt(pos) === 40) {
		pos++;
		for (; pos < max; pos++) {
			code = state.src.charCodeAt(pos);
			if (!isSpace(code) && code !== 10) break;
		}
		if (pos >= max) return false;
		start = pos;
		res = state.md.helpers.parseLinkDestination(state.src, pos, state.posMax);
		if (res.ok) {
			href = state.md.normalizeLink(res.str);
			if (state.md.validateLink(href)) pos = res.pos;
			else href = "";
		}
		start = pos;
		for (; pos < max; pos++) {
			code = state.src.charCodeAt(pos);
			if (!isSpace(code) && code !== 10) break;
		}
		res = state.md.helpers.parseLinkTitle(state.src, pos, state.posMax);
		if (pos < max && start !== pos && res.ok) {
			title = res.str;
			pos = res.pos;
			for (; pos < max; pos++) {
				code = state.src.charCodeAt(pos);
				if (!isSpace(code) && code !== 10) break;
			}
		} else title = "";
		if (pos >= max || state.src.charCodeAt(pos) !== 41) {
			state.pos = oldPos;
			return false;
		}
		pos++;
	} else {
		if (typeof state.env.references === "undefined") return false;
		if (pos < max && state.src.charCodeAt(pos) === 91) {
			start = pos + 1;
			pos = state.md.helpers.parseLinkLabel(state, pos);
			if (pos >= 0) label = state.src.slice(start, pos++);
			else pos = labelEnd + 1;
		} else pos = labelEnd + 1;
		if (!label) label = state.src.slice(labelStart, labelEnd);
		ref = state.env.references[normalizeReference(label)];
		if (!ref) {
			state.pos = oldPos;
			return false;
		}
		href = ref.href;
		title = ref.title;
	}
	if (!silent) {
		content = state.src.slice(labelStart, labelEnd);
		const tokens = [];
		state.md.inline.parse(content, state.md, state.env, tokens);
		const token = state.push("image", "img", 0);
		const attrs = [["src", href], ["alt", ""]];
		token.attrs = attrs;
		token.children = tokens;
		token.content = content;
		if (title) attrs.push(["title", title]);
	}
	state.pos = pos;
	state.posMax = max;
	return true;
}
//#endregion
//#region node_modules/markdown-it/lib/rules_inline/autolink.mjs
var EMAIL_RE = /^([a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*)$/;
var AUTOLINK_RE = /^([a-zA-Z][a-zA-Z0-9+.-]{1,31}):([^<>\x00-\x20]*)$/;
function autolink(state, silent) {
	let pos = state.pos;
	if (state.src.charCodeAt(pos) !== 60) return false;
	const start = state.pos;
	const max = state.posMax;
	for (;;) {
		if (++pos >= max) return false;
		const ch = state.src.charCodeAt(pos);
		if (ch === 60) return false;
		if (ch === 62) break;
	}
	const url = state.src.slice(start + 1, pos);
	if (AUTOLINK_RE.test(url)) {
		const fullUrl = state.md.normalizeLink(url);
		if (!state.md.validateLink(fullUrl)) return false;
		if (!silent) {
			const token_o = state.push("link_open", "a", 1);
			token_o.attrs = [["href", fullUrl]];
			token_o.markup = "autolink";
			token_o.info = "auto";
			const token_t = state.push("text", "", 0);
			token_t.content = state.md.normalizeLinkText(url);
			const token_c = state.push("link_close", "a", -1);
			token_c.markup = "autolink";
			token_c.info = "auto";
		}
		state.pos += url.length + 2;
		return true;
	}
	if (EMAIL_RE.test(url)) {
		const fullUrl = state.md.normalizeLink("mailto:" + url);
		if (!state.md.validateLink(fullUrl)) return false;
		if (!silent) {
			const token_o = state.push("link_open", "a", 1);
			token_o.attrs = [["href", fullUrl]];
			token_o.markup = "autolink";
			token_o.info = "auto";
			const token_t = state.push("text", "", 0);
			token_t.content = state.md.normalizeLinkText(url);
			const token_c = state.push("link_close", "a", -1);
			token_c.markup = "autolink";
			token_c.info = "auto";
		}
		state.pos += url.length + 2;
		return true;
	}
	return false;
}
//#endregion
//#region node_modules/markdown-it/lib/rules_inline/html_inline.mjs
function isLinkOpen(str) {
	return /^<a[>\s]/i.test(str);
}
function isLinkClose(str) {
	return /^<\/a\s*>/i.test(str);
}
function isLetter(ch) {
	const lc = ch | 32;
	return lc >= 97 && lc <= 122;
}
function html_inline(state, silent) {
	if (!state.md.options.html) return false;
	const max = state.posMax;
	const pos = state.pos;
	if (state.src.charCodeAt(pos) !== 60 || pos + 2 >= max) return false;
	const ch = state.src.charCodeAt(pos + 1);
	if (ch !== 33 && ch !== 63 && ch !== 47 && !isLetter(ch)) return false;
	const match = state.src.slice(pos).match(HTML_TAG_RE);
	if (!match) return false;
	if (!silent) {
		const token = state.push("html_inline", "", 0);
		token.content = match[0];
		if (isLinkOpen(token.content)) state.linkLevel++;
		if (isLinkClose(token.content)) state.linkLevel--;
	}
	state.pos += match[0].length;
	return true;
}
//#endregion
//#region node_modules/markdown-it/lib/rules_inline/entity.mjs
var DIGITAL_RE = /^&#((?:x[a-f0-9]{1,6}|[0-9]{1,7}));/i;
var NAMED_RE = /^&([a-z][a-z0-9]{1,31});/i;
function entity(state, silent) {
	const pos = state.pos;
	const max = state.posMax;
	if (state.src.charCodeAt(pos) !== 38) return false;
	if (pos + 1 >= max) return false;
	if (state.src.charCodeAt(pos + 1) === 35) {
		const match = state.src.slice(pos).match(DIGITAL_RE);
		if (match) {
			if (!silent) {
				const code = match[1][0].toLowerCase() === "x" ? parseInt(match[1].slice(1), 16) : parseInt(match[1], 10);
				const token = state.push("text_special", "", 0);
				token.content = isValidEntityCode(code) ? fromCodePoint(code) : fromCodePoint(65533);
				token.markup = match[0];
				token.info = "entity";
			}
			state.pos += match[0].length;
			return true;
		}
	} else {
		const match = state.src.slice(pos).match(NAMED_RE);
		if (match) {
			const decoded = decodeHTMLStrict(match[0]);
			if (decoded !== match[0]) {
				if (!silent) {
					const token = state.push("text_special", "", 0);
					token.content = decoded;
					token.markup = match[0];
					token.info = "entity";
				}
				state.pos += match[0].length;
				return true;
			}
		}
	}
	return false;
}
//#endregion
//#region node_modules/markdown-it/lib/rules_inline/balance_pairs.mjs
function processDelimiters(delimiters) {
	const openersBottom = {};
	const max = delimiters.length;
	if (!max) return;
	let headerIdx = 0;
	let lastTokenIdx = -2;
	const jumps = [];
	for (let closerIdx = 0; closerIdx < max; closerIdx++) {
		const closer = delimiters[closerIdx];
		jumps.push(0);
		if (delimiters[headerIdx].marker !== closer.marker || lastTokenIdx !== closer.token - 1) headerIdx = closerIdx;
		lastTokenIdx = closer.token;
		closer.length = closer.length || 0;
		if (!closer.close) continue;
		if (!openersBottom.hasOwnProperty(closer.marker)) openersBottom[closer.marker] = [
			-1,
			-1,
			-1,
			-1,
			-1,
			-1
		];
		const minOpenerIdx = openersBottom[closer.marker][(closer.open ? 3 : 0) + closer.length % 3];
		let openerIdx = headerIdx - jumps[headerIdx] - 1;
		let newMinOpenerIdx = openerIdx;
		for (; openerIdx > minOpenerIdx; openerIdx -= jumps[openerIdx] + 1) {
			const opener = delimiters[openerIdx];
			if (opener.marker !== closer.marker) continue;
			if (opener.open && opener.end < 0) {
				let isOddMatch = false;
				if (opener.close || closer.open) {
					if ((opener.length + closer.length) % 3 === 0) {
						if (opener.length % 3 !== 0 || closer.length % 3 !== 0) isOddMatch = true;
					}
				}
				if (!isOddMatch) {
					const lastJump = openerIdx > 0 && !delimiters[openerIdx - 1].open ? jumps[openerIdx - 1] + 1 : 0;
					jumps[closerIdx] = closerIdx - openerIdx + lastJump;
					jumps[openerIdx] = lastJump;
					closer.open = false;
					opener.end = closerIdx;
					opener.close = false;
					newMinOpenerIdx = -1;
					lastTokenIdx = -2;
					break;
				}
			}
		}
		if (newMinOpenerIdx !== -1) openersBottom[closer.marker][(closer.open ? 3 : 0) + (closer.length || 0) % 3] = newMinOpenerIdx;
	}
}
function link_pairs(state) {
	const tokens_meta = state.tokens_meta;
	const max = state.tokens_meta.length;
	processDelimiters(state.delimiters);
	for (let curr = 0; curr < max; curr++) if (tokens_meta[curr] && tokens_meta[curr].delimiters) processDelimiters(tokens_meta[curr].delimiters);
}
//#endregion
//#region node_modules/markdown-it/lib/rules_inline/fragments_join.mjs
function fragments_join(state) {
	let curr, last;
	let level = 0;
	const tokens = state.tokens;
	const max = state.tokens.length;
	for (curr = last = 0; curr < max; curr++) {
		if (tokens[curr].nesting < 0) level--;
		tokens[curr].level = level;
		if (tokens[curr].nesting > 0) level++;
		if (tokens[curr].type === "text" && curr + 1 < max && tokens[curr + 1].type === "text") tokens[curr + 1].content = tokens[curr].content + tokens[curr + 1].content;
		else {
			if (curr !== last) tokens[last] = tokens[curr];
			last++;
		}
	}
	if (curr !== last) tokens.length = last;
}
//#endregion
//#region node_modules/markdown-it/lib/parser_inline.mjs
/** internal
* class ParserInline
*
* Tokenizes paragraph content.
**/
var _rules = [
	["text", text],
	["linkify", linkify],
	["newline", newline],
	["escape", escape],
	["backticks", backtick],
	["strikethrough", strikethrough_default.tokenize],
	["emphasis", emphasis_default.tokenize],
	["link", link],
	["image", image],
	["autolink", autolink],
	["html_inline", html_inline],
	["entity", entity]
];
var _rules2 = [
	["balance_pairs", link_pairs],
	["strikethrough", strikethrough_default.postProcess],
	["emphasis", emphasis_default.postProcess],
	["fragments_join", fragments_join]
];
/**
* new ParserInline()
**/
function ParserInline() {
	/**
	* ParserInline#ruler -> Ruler
	*
	* [[Ruler]] instance. Keep configuration of inline rules.
	**/
	this.ruler = new Ruler();
	for (let i = 0; i < _rules.length; i++) this.ruler.push(_rules[i][0], _rules[i][1]);
	/**
	* ParserInline#ruler2 -> Ruler
	*
	* [[Ruler]] instance. Second ruler used for post-processing
	* (e.g. in emphasis-like rules).
	**/
	this.ruler2 = new Ruler();
	for (let i = 0; i < _rules2.length; i++) this.ruler2.push(_rules2[i][0], _rules2[i][1]);
}
ParserInline.prototype.skipToken = function(state) {
	const pos = state.pos;
	const rules = this.ruler.getRules("");
	const len = rules.length;
	const maxNesting = state.md.options.maxNesting;
	const cache = state.cache;
	if (typeof cache[pos] !== "undefined") {
		state.pos = cache[pos];
		return;
	}
	let ok = false;
	if (state.level < maxNesting) for (let i = 0; i < len; i++) {
		state.level++;
		ok = rules[i](state, true);
		state.level--;
		if (ok) {
			if (pos >= state.pos) throw new Error("inline rule didn't increment state.pos");
			break;
		}
	}
	else state.pos = state.posMax;
	if (!ok) state.pos++;
	cache[pos] = state.pos;
};
ParserInline.prototype.tokenize = function(state) {
	const rules = this.ruler.getRules("");
	const len = rules.length;
	const end = state.posMax;
	const maxNesting = state.md.options.maxNesting;
	while (state.pos < end) {
		const prevPos = state.pos;
		let ok = false;
		if (state.level < maxNesting) for (let i = 0; i < len; i++) {
			ok = rules[i](state, false);
			if (ok) {
				if (prevPos >= state.pos) throw new Error("inline rule didn't increment state.pos");
				break;
			}
		}
		if (ok) {
			if (state.pos >= end) break;
			continue;
		}
		state.pending += state.src[state.pos++];
	}
	if (state.pending) state.pushPending();
};
/**
* ParserInline.parse(str, md, env, outTokens)
*
* Process input string and push inline tokens into `outTokens`
**/
ParserInline.prototype.parse = function(str, md, env, outTokens) {
	const state = new this.State(str, md, env, outTokens);
	this.tokenize(state);
	const rules = this.ruler2.getRules("");
	const len = rules.length;
	for (let i = 0; i < len; i++) rules[i](state);
};
ParserInline.prototype.State = StateInline;
//#endregion
//#region node_modules/linkify-it/lib/re.mjs
function re_default(opts) {
	const re = {};
	opts = opts || {};
	re.src_Any = regex_default$5.source;
	re.src_Cc = regex_default$4.source;
	re.src_Z = regex_default.source;
	re.src_P = regex_default$2.source;
	re.src_ZPCc = [
		re.src_Z,
		re.src_P,
		re.src_Cc
	].join("|");
	re.src_ZCc = [re.src_Z, re.src_Cc].join("|");
	const text_separators = "[><｜]";
	re.src_pseudo_letter = `(?:(?!${text_separators}|${re.src_ZPCc})${re.src_Any})`;
	re.src_ip4 = "(?:(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)";
	re.src_auth = `(?:(?:(?!${re.src_ZCc}|[@/\\[\\]()]).){1,50}@)?`;
	re.src_port = "(?::(?:6(?:[0-4]\\d{3}|5(?:[0-4]\\d{2}|5(?:[0-2]\\d|3[0-5])))|[1-5]?\\d{1,4}))?";
	re.src_host_terminator = `(?=$|${text_separators}|${re.src_ZPCc})(?!${opts["---"] ? "-(?!--)|" : "-|"}_|:\\d|\\.-|\\.(?!$|${re.src_ZPCc}))`;
	re.src_path = `(?:[/?#](?:(?!${re.src_ZCc}|${text_separators}|[()[\\]{}.,"'?!\\-;]).|\\[(?:(?!${re.src_ZCc}|\\]).)*\\]|\\((?:(?!${re.src_ZCc}|[)]).)*\\)|\\{(?:(?!${re.src_ZCc}|[}]).)*\\}|\\"(?:(?!${re.src_ZCc}|["]).)+\\"|\\'(?:(?!${re.src_ZCc}|[']).)+\\'|\\'(?=${re.src_pseudo_letter}|[-])|\\.{2,}[a-zA-Z0-9%/&]|\\.(?!${re.src_ZCc}|[.]|$)|` + (opts["---"] ? "\\-(?!--(?:[^-]|$))(?:-*)|" : "\\-+|") + `,(?!${re.src_ZCc}|$)|;(?!${re.src_ZCc}|$)|\\!+(?!${re.src_ZCc}|[!]|$)|\\?(?!${re.src_ZCc}|[?]|$))+|\\/)?`;
	re.src_email_name = "[\\-;:&=\\+\\$,\\.a-zA-Z0-9_][\\-;:&=\\+\\$,\\\"\\.a-zA-Z0-9_]{0,63}";
	re.src_xn = "xn--[a-z0-9\\-]{1,59}";
	re.src_domain_root = "(?:" + re.src_xn + `|${re.src_pseudo_letter}{1,63})`;
	re.src_domain = "(?:" + re.src_xn + `|(?:${re.src_pseudo_letter})|(?:${re.src_pseudo_letter}(?:-|${re.src_pseudo_letter}){0,61}${re.src_pseudo_letter}))`;
	re.src_host = `(?:(?:(?:(?:${re.src_domain})\\.)*${re.src_domain}))`;
	re.tpl_host_fuzzy = "(?:" + re.src_ip4 + `|(?:(?:(?:${re.src_domain})\\.)+(?:%TLDS%)))`;
	re.tpl_host_no_ip_fuzzy = `(?:(?:(?:${re.src_domain})\\.)+(?:%TLDS%))`;
	re.src_host_strict = re.src_host + re.src_host_terminator;
	re.tpl_host_fuzzy_strict = re.tpl_host_fuzzy + re.src_host_terminator;
	re.src_host_port_strict = re.src_host + re.src_port + re.src_host_terminator;
	re.tpl_host_port_fuzzy_strict = re.tpl_host_fuzzy + re.src_port + re.src_host_terminator;
	re.tpl_host_port_no_ip_fuzzy_strict = re.tpl_host_no_ip_fuzzy + re.src_port + re.src_host_terminator;
	re.tpl_host_fuzzy_test = `localhost|www\\.|\\.\\d{1,3}\\.|(?:\\.(?:%TLDS%)(?:${re.src_ZPCc}|>|$))`;
	re.tpl_email_fuzzy = `(^|${text_separators}|"|\\(|${re.src_ZCc})(${re.src_email_name}@${re.tpl_host_fuzzy_strict})`;
	re.tpl_link_fuzzy = `(^|(?![.:/\\-_@])(?:[$+<=>^\`|\uff5c]|${re.src_ZPCc}))((?![$+<=>^\`|\uff5c])${re.tpl_host_port_fuzzy_strict}${re.src_path})`;
	re.tpl_link_no_ip_fuzzy = `(^|(?![.:/\\-_@])(?:[$+<=>^\`|\uff5c]|${re.src_ZPCc}))((?![$+<=>^\`|\uff5c])${re.tpl_host_port_no_ip_fuzzy_strict}${re.src_path})`;
	return re;
}
//#endregion
//#region node_modules/linkify-it/index.mjs
function assign(obj) {
	Array.prototype.slice.call(arguments, 1).forEach(function(source) {
		if (!source) return;
		Object.keys(source).forEach(function(key) {
			obj[key] = source[key];
		});
	});
	return obj;
}
function _class(obj) {
	return Object.prototype.toString.call(obj);
}
function isString(obj) {
	return _class(obj) === "[object String]";
}
function isObject(obj) {
	return _class(obj) === "[object Object]";
}
function isRegExp(obj) {
	return _class(obj) === "[object RegExp]";
}
function isFunction(obj) {
	return _class(obj) === "[object Function]";
}
function escapeRE(str) {
	return str.replace(/[.?*+^$[\]\\(){}|-]/g, "\\$&");
}
var defaultOptions = {
	fuzzyLink: true,
	fuzzyEmail: true,
	fuzzyIP: false
};
function isOptionsObj(obj) {
	return Object.keys(obj || {}).reduce(function(acc, k) {
		return acc || defaultOptions.hasOwnProperty(k);
	}, false);
}
var defaultSchemas = {
	"http:": { validate: function(text, pos, self) {
		const tail = text.slice(pos);
		if (!self.re.http) self.re.http = new RegExp(`^\\/\\/${self.re.src_auth}${self.re.src_host_port_strict}${self.re.src_path}`, "i");
		if (self.re.http.test(tail)) return tail.match(self.re.http)[0].length;
		return 0;
	} },
	"https:": "http:",
	"ftp:": "http:",
	"//": { validate: function(text, pos, self) {
		const tail = text.slice(pos);
		if (!self.re.no_http) self.re.no_http = new RegExp("^" + self.re.src_auth + `(?:localhost|(?:(?:${self.re.src_domain})\\.)+${self.re.src_domain_root})` + self.re.src_port + self.re.src_host_terminator + self.re.src_path, "i");
		if (self.re.no_http.test(tail)) {
			if (pos >= 3 && text[pos - 3] === ":") return 0;
			if (pos >= 3 && text[pos - 3] === "/") return 0;
			return tail.match(self.re.no_http)[0].length;
		}
		return 0;
	} },
	"mailto:": { validate: function(text, pos, self) {
		const tail = text.slice(pos);
		if (!self.re.mailto) self.re.mailto = new RegExp(`^${self.re.src_email_name}@${self.re.src_host_strict}`, "i");
		if (self.re.mailto.test(tail)) return tail.match(self.re.mailto)[0].length;
		return 0;
	} }
};
var tlds_2ch_src_re = "a[cdefgilmnoqrstuwxz]|b[abdefghijmnorstvwyz]|c[acdfghiklmnoruvwxyz]|d[ejkmoz]|e[cegrstu]|f[ijkmor]|g[abdefghilmnpqrstuwy]|h[kmnrtu]|i[delmnoqrst]|j[emop]|k[eghimnprwyz]|l[abcikrstuvy]|m[acdeghklmnopqrstuvwxyz]|n[acefgilopruz]|om|p[aefghklmnrstwy]|qa|r[eosuw]|s[abcdeghijklmnortuvxyz]|t[cdfghjklmnortvwz]|u[agksyz]|v[aceginu]|w[fs]|y[et]|z[amw]";
var tlds_default = "biz|com|edu|gov|net|org|pro|web|xxx|aero|asia|coop|info|museum|name|shop|рф".split("|");
function createValidator(re) {
	return function(text, pos) {
		const tail = text.slice(pos);
		if (re.test(tail)) return tail.match(re)[0].length;
		return 0;
	};
}
function createNormalizer() {
	return function(match, self) {
		self.normalize(match);
	};
}
function compile(self) {
	const re = self.re = re_default(self.__opts__);
	const tlds = self.__tlds__.slice();
	self.onCompile();
	if (!self.__tlds_replaced__) tlds.push(tlds_2ch_src_re);
	tlds.push(re.src_xn);
	re.src_tlds = tlds.join("|");
	function untpl(tpl) {
		return tpl.replace("%TLDS%", re.src_tlds);
	}
	re.email_fuzzy = RegExp(untpl(re.tpl_email_fuzzy), "i");
	re.email_fuzzy_global = RegExp(untpl(re.tpl_email_fuzzy), "ig");
	re.link_fuzzy = RegExp(untpl(re.tpl_link_fuzzy), "i");
	re.link_fuzzy_global = RegExp(untpl(re.tpl_link_fuzzy), "ig");
	re.link_no_ip_fuzzy = RegExp(untpl(re.tpl_link_no_ip_fuzzy), "i");
	re.link_no_ip_fuzzy_global = RegExp(untpl(re.tpl_link_no_ip_fuzzy), "ig");
	re.host_fuzzy_test = RegExp(untpl(re.tpl_host_fuzzy_test), "i");
	const aliases = [];
	self.__compiled__ = {};
	function schemaError(name, val) {
		throw new Error(`(LinkifyIt) Invalid schema "${name}": ${val}`);
	}
	Object.keys(self.__schemas__).forEach(function(name) {
		const val = self.__schemas__[name];
		if (val === null) return;
		const compiled = {
			validate: null,
			link: null
		};
		self.__compiled__[name] = compiled;
		if (isObject(val)) {
			if (isRegExp(val.validate)) compiled.validate = createValidator(val.validate);
			else if (isFunction(val.validate)) compiled.validate = val.validate;
			else schemaError(name, val);
			if (isFunction(val.normalize)) compiled.normalize = val.normalize;
			else if (!val.normalize) compiled.normalize = createNormalizer();
			else schemaError(name, val);
			return;
		}
		if (isString(val)) {
			aliases.push(name);
			return;
		}
		schemaError(name, val);
	});
	aliases.forEach(function(alias) {
		if (!self.__compiled__[self.__schemas__[alias]]) return;
		self.__compiled__[alias].validate = self.__compiled__[self.__schemas__[alias]].validate;
		self.__compiled__[alias].normalize = self.__compiled__[self.__schemas__[alias]].normalize;
	});
	self.__compiled__[""] = {
		validate: null,
		normalize: createNormalizer()
	};
	const slist = Object.keys(self.__compiled__).filter(function(name) {
		return name.length > 0 && self.__compiled__[name];
	}).map(escapeRE).join("|");
	self.re.schema_test = RegExp(`(^|(?!_)(?:[><\uff5c]|${re.src_ZPCc}))(${slist})`, "i");
	self.re.schema_search = RegExp(`(^|(?!_)(?:[><\uff5c]|${re.src_ZPCc}))(${slist})`, "ig");
	self.re.schema_at_start = RegExp(`^${self.re.schema_search.source}`, "i");
	self.re.pretest = RegExp(`(${self.re.schema_test.source})|(${self.re.host_fuzzy_test.source})|@`, "i");
}
/**
* class Match
*
* Match result. Single element of array, returned by [[LinkifyIt#match]]
**/
function Match(text, schema, index, lastIndex) {
	const raw = text.slice(index, lastIndex);
	/**
	* Match#schema -> String
	*
	* Prefix (protocol) for matched string.
	**/
	this.schema = schema.toLowerCase();
	/**
	* Match#index -> Number
	*
	* First position of matched string.
	**/
	this.index = index;
	/**
	* Match#lastIndex -> Number
	*
	* Next position after matched string.
	**/
	this.lastIndex = lastIndex;
	/**
	* Match#raw -> String
	*
	* Matched string.
	**/
	this.raw = raw;
	/**
	* Match#text -> String
	*
	* Notmalized text of matched string.
	**/
	this.text = raw;
	/**
	* Match#url -> String
	*
	* Normalized url of matched string.
	**/
	this.url = raw;
}
/**
* class LinkifyIt
**/
/**
* new LinkifyIt(schemas, options)
* - schemas (Object): Optional. Additional schemas to validate (prefix/validator)
* - options (Object): { fuzzyLink|fuzzyEmail|fuzzyIP: true|false }
*
* Creates new linkifier instance with optional additional schemas.
* Can be called without `new` keyword for convenience.
*
* By default understands:
*
* - `http(s)://...` , `ftp://...`, `mailto:...` & `//...` links
* - "fuzzy" links and emails (example.com, foo@bar.com).
*
* `schemas` is an object, where each key/value describes protocol/rule:
*
* - __key__ - link prefix (usually, protocol name with `:` at the end, `skype:`
*   for example). `linkify-it` makes shure that prefix is not preceeded with
*   alphanumeric char and symbols. Only whitespaces and punctuation allowed.
* - __value__ - rule to check tail after link prefix
*   - _String_ - just alias to existing rule
*   - _Object_
*     - _validate_ - validator function (should return matched length on success),
*       or `RegExp`.
*     - _normalize_ - optional function to normalize text & url of matched result
*       (for example, for @twitter mentions).
*
* `options`:
*
* - __fuzzyLink__ - recognige URL-s without `http(s):` prefix. Default `true`.
* - __fuzzyIP__ - allow IPs in fuzzy links above. Can conflict with some texts
*   like version numbers. Default `false`.
* - __fuzzyEmail__ - recognize emails without `mailto:` prefix.
*
**/
function LinkifyIt(schemas, options) {
	if (!(this instanceof LinkifyIt)) return new LinkifyIt(schemas, options);
	if (!options) {
		if (isOptionsObj(schemas)) {
			options = schemas;
			schemas = {};
		}
	}
	this.__opts__ = assign({}, defaultOptions, options);
	this.__schemas__ = assign({}, defaultSchemas, schemas);
	this.__compiled__ = {};
	this.__tlds__ = tlds_default;
	this.__tlds_replaced__ = false;
	this.re = {};
	compile(this);
}
/** chainable
* LinkifyIt#add(schema, definition)
* - schema (String): rule name (fixed pattern prefix)
* - definition (String|RegExp|Object): schema definition
*
* Add new rule definition. See constructor description for details.
**/
LinkifyIt.prototype.add = function add(schema, definition) {
	this.__schemas__[schema] = definition;
	compile(this);
	return this;
};
/** chainable
* LinkifyIt#set(options)
* - options (Object): { fuzzyLink|fuzzyEmail|fuzzyIP: true|false }
*
* Set recognition options for links without schema.
**/
LinkifyIt.prototype.set = function set(options) {
	this.__opts__ = assign(this.__opts__, options);
	return this;
};
/**
* LinkifyIt#test(text) -> Boolean
*
* Searches linkifiable pattern and returns `true` on success or `false` on fail.
**/
LinkifyIt.prototype.test = function test(text) {
	if (!text.length) return false;
	let m, re;
	if (this.re.schema_test.test(text)) {
		re = this.re.schema_search;
		re.lastIndex = 0;
		while ((m = re.exec(text)) !== null) if (this.testSchemaAt(text, m[2], re.lastIndex)) return true;
	}
	if (this.__opts__.fuzzyLink && this.__compiled__["http:"]) {
		if (text.search(this.re.host_fuzzy_test) >= 0) {
			if (text.match(this.__opts__.fuzzyIP ? this.re.link_fuzzy : this.re.link_no_ip_fuzzy) !== null) return true;
		}
	}
	if (this.__opts__.fuzzyEmail && this.__compiled__["mailto:"]) {
		if (text.indexOf("@") >= 0) {
			if (text.match(this.re.email_fuzzy) !== null) return true;
		}
	}
	return false;
};
/**
* LinkifyIt#pretest(text) -> Boolean
*
* Very quick check, that can give false positives. Returns true if link MAY BE
* can exists. Can be used for speed optimization, when you need to check that
* link NOT exists.
**/
LinkifyIt.prototype.pretest = function pretest(text) {
	return this.re.pretest.test(text);
};
/**
* LinkifyIt#testSchemaAt(text, name, position) -> Number
* - text (String): text to scan
* - name (String): rule (schema) name
* - position (Number): text offset to check from
*
* Similar to [[LinkifyIt#test]] but checks only specific protocol tail exactly
* at given position. Returns length of found pattern (0 on fail).
**/
LinkifyIt.prototype.testSchemaAt = function testSchemaAt(text, schema, pos) {
	if (!this.__compiled__[schema.toLowerCase()]) return 0;
	return this.__compiled__[schema.toLowerCase()].validate(text, pos, this);
};
/**
* LinkifyIt#match(text) -> Array|null
*
* Returns array of found link descriptions or `null` on fail. We strongly
* recommend to use [[LinkifyIt#test]] first, for best speed.
*
* ##### Result match description
*
* - __schema__ - link schema, can be empty for fuzzy links, or `//` for
*   protocol-neutral  links.
* - __index__ - offset of matched text
* - __lastIndex__ - index of next char after mathch end
* - __raw__ - matched text
* - __text__ - normalized text
* - __url__ - link, generated from matched text
**/
LinkifyIt.prototype.match = function match(text) {
	const result = [];
	const type_schemed = [];
	const type_fuzzy_link = [];
	const type_fuzzy_email = [];
	let m, len, re;
	function choose(a, b) {
		if (!a) return b;
		if (!b) return a;
		if (a.index !== b.index) return a.index < b.index ? a : b;
		return a.lastIndex >= b.lastIndex ? a : b;
	}
	if (!text.length) return null;
	if (this.re.schema_test.test(text)) {
		re = this.re.schema_search;
		re.lastIndex = 0;
		while ((m = re.exec(text)) !== null) {
			len = this.testSchemaAt(text, m[2], re.lastIndex);
			if (len) type_schemed.push({
				schema: m[2],
				index: m.index + m[1].length,
				lastIndex: m.index + m[0].length + len
			});
		}
	}
	if (this.__opts__.fuzzyLink && this.__compiled__["http:"]) {
		re = this.__opts__.fuzzyIP ? this.re.link_fuzzy_global : this.re.link_no_ip_fuzzy_global;
		re.lastIndex = 0;
		while ((m = re.exec(text)) !== null) type_fuzzy_link.push({
			schema: "",
			index: m.index + m[1].length,
			lastIndex: m.index + m[0].length
		});
	}
	if (this.__opts__.fuzzyEmail && this.__compiled__["mailto:"]) {
		re = this.re.email_fuzzy_global;
		re.lastIndex = 0;
		while ((m = re.exec(text)) !== null) type_fuzzy_email.push({
			schema: "mailto:",
			index: m.index + m[1].length,
			lastIndex: m.index + m[0].length
		});
	}
	const indexes = [
		0,
		0,
		0
	];
	let lastIndex = 0;
	for (;;) {
		const candidates = [
			type_schemed[indexes[0]],
			type_fuzzy_email[indexes[1]],
			type_fuzzy_link[indexes[2]]
		];
		const candidate = choose(choose(candidates[0], candidates[1]), candidates[2]);
		if (!candidate) break;
		if (candidate === candidates[0]) indexes[0]++;
		else if (candidate === candidates[1]) indexes[1]++;
		else indexes[2]++;
		if (candidate.index < lastIndex) continue;
		const match = new Match(text, candidate.schema, candidate.index, candidate.lastIndex);
		this.__compiled__[match.schema].normalize(match, this);
		result.push(match);
		lastIndex = candidate.lastIndex;
	}
	if (result.length) return result;
	return null;
};
/**
* LinkifyIt#matchAtStart(text) -> Match|null
*
* Returns fully-formed (not fuzzy) link if it starts at the beginning
* of the string, and null otherwise.
**/
LinkifyIt.prototype.matchAtStart = function matchAtStart(text) {
	if (!text.length) return null;
	const m = this.re.schema_at_start.exec(text);
	if (!m) return null;
	const len = this.testSchemaAt(text, m[2], m[0].length);
	if (!len) return null;
	const match = new Match(text, m[2], m.index + m[1].length, m.index + m[0].length + len);
	this.__compiled__[match.schema].normalize(match, this);
	return match;
};
/** chainable
* LinkifyIt#tlds(list [, keepOld]) -> this
* - list (Array): list of tlds
* - keepOld (Boolean): merge with current list if `true` (`false` by default)
*
* Load (or merge) new tlds list. Those are user for fuzzy links (without prefix)
* to avoid false positives. By default this algorythm used:
*
* - hostname with any 2-letter root zones are ok.
* - biz|com|edu|gov|net|org|pro|web|xxx|aero|asia|coop|info|museum|name|shop|рф
*   are ok.
* - encoded (`xn--...`) root zones are ok.
*
* If list is replaced, then exact match for 2-chars root zones will be checked.
**/
LinkifyIt.prototype.tlds = function tlds(list, keepOld) {
	list = Array.isArray(list) ? list : [list];
	if (!keepOld) {
		this.__tlds__ = list.slice();
		this.__tlds_replaced__ = true;
		compile(this);
		return this;
	}
	this.__tlds__ = this.__tlds__.concat(list).sort().filter(function(el, idx, arr) {
		return el !== arr[idx - 1];
	}).reverse();
	compile(this);
	return this;
};
/**
* LinkifyIt#normalize(match)
*
* Default normalizer (if schema does not define it's own).
**/
LinkifyIt.prototype.normalize = function normalize(match) {
	if (!match.schema) match.url = `http://${match.url}`;
	if (match.schema === "mailto:" && !/^mailto:/i.test(match.url)) match.url = `mailto:${match.url}`;
};
/**
* LinkifyIt#onCompile()
*
* Override to modify basic RegExp-s.
**/
LinkifyIt.prototype.onCompile = function onCompile() {};
//#endregion
//#region node_modules/punycode.js/punycode.es6.js
/** Highest positive signed 32-bit float value */
var maxInt = 2147483647;
/** Bootstring parameters */
var base = 36;
var tMin = 1;
var tMax = 26;
var skew = 38;
var damp = 700;
var initialBias = 72;
var initialN = 128;
var delimiter = "-";
/** Regular expressions */
var regexPunycode = /^xn--/;
var regexNonASCII = /[^\0-\x7F]/;
var regexSeparators = /[\x2E\u3002\uFF0E\uFF61]/g;
/** Error messages */
var errors = {
	"overflow": "Overflow: input needs wider integers to process",
	"not-basic": "Illegal input >= 0x80 (not a basic code point)",
	"invalid-input": "Invalid input"
};
/** Convenience shortcuts */
var baseMinusTMin = base - tMin;
var floor = Math.floor;
var stringFromCharCode = String.fromCharCode;
/**
* A generic error utility function.
* @private
* @param {String} type The error type.
* @returns {Error} Throws a `RangeError` with the applicable error message.
*/
function error(type) {
	throw new RangeError(errors[type]);
}
/**
* A generic `Array#map` utility function.
* @private
* @param {Array} array The array to iterate over.
* @param {Function} callback The function that gets called for every array
* item.
* @returns {Array} A new array of values returned by the callback function.
*/
function map(array, callback) {
	const result = [];
	let length = array.length;
	while (length--) result[length] = callback(array[length]);
	return result;
}
/**
* A simple `Array#map`-like wrapper to work with domain name strings or email
* addresses.
* @private
* @param {String} domain The domain name or email address.
* @param {Function} callback The function that gets called for every
* character.
* @returns {String} A new string of characters returned by the callback
* function.
*/
function mapDomain(domain, callback) {
	const parts = domain.split("@");
	let result = "";
	if (parts.length > 1) {
		result = parts[0] + "@";
		domain = parts[1];
	}
	domain = domain.replace(regexSeparators, ".");
	const encoded = map(domain.split("."), callback).join(".");
	return result + encoded;
}
/**
* Creates an array containing the numeric code points of each Unicode
* character in the string. While JavaScript uses UCS-2 internally,
* this function will convert a pair of surrogate halves (each of which
* UCS-2 exposes as separate characters) into a single code point,
* matching UTF-16.
* @see `punycode.ucs2.encode`
* @see <https://mathiasbynens.be/notes/javascript-encoding>
* @memberOf punycode.ucs2
* @name decode
* @param {String} string The Unicode input string (UCS-2).
* @returns {Array} The new array of code points.
*/
function ucs2decode(string) {
	const output = [];
	let counter = 0;
	const length = string.length;
	while (counter < length) {
		const value = string.charCodeAt(counter++);
		if (value >= 55296 && value <= 56319 && counter < length) {
			const extra = string.charCodeAt(counter++);
			if ((extra & 64512) == 56320) output.push(((value & 1023) << 10) + (extra & 1023) + 65536);
			else {
				output.push(value);
				counter--;
			}
		} else output.push(value);
	}
	return output;
}
/**
* Creates a string based on an array of numeric code points.
* @see `punycode.ucs2.decode`
* @memberOf punycode.ucs2
* @name encode
* @param {Array} codePoints The array of numeric code points.
* @returns {String} The new Unicode string (UCS-2).
*/
var ucs2encode = (codePoints) => String.fromCodePoint(...codePoints);
/**
* Converts a basic code point into a digit/integer.
* @see `digitToBasic()`
* @private
* @param {Number} codePoint The basic numeric code point value.
* @returns {Number} The numeric value of a basic code point (for use in
* representing integers) in the range `0` to `base - 1`, or `base` if
* the code point does not represent a value.
*/
var basicToDigit = function(codePoint) {
	if (codePoint >= 48 && codePoint < 58) return 26 + (codePoint - 48);
	if (codePoint >= 65 && codePoint < 91) return codePoint - 65;
	if (codePoint >= 97 && codePoint < 123) return codePoint - 97;
	return base;
};
/**
* Converts a digit/integer into a basic code point.
* @see `basicToDigit()`
* @private
* @param {Number} digit The numeric value of a basic code point.
* @returns {Number} The basic code point whose value (when used for
* representing integers) is `digit`, which needs to be in the range
* `0` to `base - 1`. If `flag` is non-zero, the uppercase form is
* used; else, the lowercase form is used. The behavior is undefined
* if `flag` is non-zero and `digit` has no uppercase form.
*/
var digitToBasic = function(digit, flag) {
	return digit + 22 + 75 * (digit < 26) - ((flag != 0) << 5);
};
/**
* Bias adaptation function as per section 3.4 of RFC 3492.
* https://tools.ietf.org/html/rfc3492#section-3.4
* @private
*/
var adapt = function(delta, numPoints, firstTime) {
	let k = 0;
	delta = firstTime ? floor(delta / damp) : delta >> 1;
	delta += floor(delta / numPoints);
	for (; delta > 455; k += base) delta = floor(delta / baseMinusTMin);
	return floor(k + 36 * delta / (delta + skew));
};
/**
* Converts a Punycode string of ASCII-only symbols to a string of Unicode
* symbols.
* @memberOf punycode
* @param {String} input The Punycode string of ASCII-only symbols.
* @returns {String} The resulting string of Unicode symbols.
*/
var decode = function(input) {
	const output = [];
	const inputLength = input.length;
	let i = 0;
	let n = initialN;
	let bias = initialBias;
	let basic = input.lastIndexOf(delimiter);
	if (basic < 0) basic = 0;
	for (let j = 0; j < basic; ++j) {
		if (input.charCodeAt(j) >= 128) error("not-basic");
		output.push(input.charCodeAt(j));
	}
	for (let index = basic > 0 ? basic + 1 : 0; index < inputLength;) {
		const oldi = i;
		for (let w = 1, k = base;; k += base) {
			if (index >= inputLength) error("invalid-input");
			const digit = basicToDigit(input.charCodeAt(index++));
			if (digit >= base) error("invalid-input");
			if (digit > floor((maxInt - i) / w)) error("overflow");
			i += digit * w;
			const t = k <= bias ? tMin : k >= bias + tMax ? tMax : k - bias;
			if (digit < t) break;
			const baseMinusT = base - t;
			if (w > floor(maxInt / baseMinusT)) error("overflow");
			w *= baseMinusT;
		}
		const out = output.length + 1;
		bias = adapt(i - oldi, out, oldi == 0);
		if (floor(i / out) > maxInt - n) error("overflow");
		n += floor(i / out);
		i %= out;
		output.splice(i++, 0, n);
	}
	return String.fromCodePoint(...output);
};
/**
* Converts a string of Unicode symbols (e.g. a domain name label) to a
* Punycode string of ASCII-only symbols.
* @memberOf punycode
* @param {String} input The string of Unicode symbols.
* @returns {String} The resulting Punycode string of ASCII-only symbols.
*/
var encode = function(input) {
	const output = [];
	input = ucs2decode(input);
	const inputLength = input.length;
	let n = initialN;
	let delta = 0;
	let bias = initialBias;
	for (const currentValue of input) if (currentValue < 128) output.push(stringFromCharCode(currentValue));
	const basicLength = output.length;
	let handledCPCount = basicLength;
	if (basicLength) output.push(delimiter);
	while (handledCPCount < inputLength) {
		let m = maxInt;
		for (const currentValue of input) if (currentValue >= n && currentValue < m) m = currentValue;
		const handledCPCountPlusOne = handledCPCount + 1;
		if (m - n > floor((maxInt - delta) / handledCPCountPlusOne)) error("overflow");
		delta += (m - n) * handledCPCountPlusOne;
		n = m;
		for (const currentValue of input) {
			if (currentValue < n && ++delta > maxInt) error("overflow");
			if (currentValue === n) {
				let q = delta;
				for (let k = base;; k += base) {
					const t = k <= bias ? tMin : k >= bias + tMax ? tMax : k - bias;
					if (q < t) break;
					const qMinusT = q - t;
					const baseMinusT = base - t;
					output.push(stringFromCharCode(digitToBasic(t + qMinusT % baseMinusT, 0)));
					q = floor(qMinusT / baseMinusT);
				}
				output.push(stringFromCharCode(digitToBasic(q, 0)));
				bias = adapt(delta, handledCPCountPlusOne, handledCPCount === basicLength);
				delta = 0;
				++handledCPCount;
			}
		}
		++delta;
		++n;
	}
	return output.join("");
};
/**
* Converts a Punycode string representing a domain name or an email address
* to Unicode. Only the Punycoded parts of the input will be converted, i.e.
* it doesn't matter if you call it on a string that has already been
* converted to Unicode.
* @memberOf punycode
* @param {String} input The Punycoded domain name or email address to
* convert to Unicode.
* @returns {String} The Unicode representation of the given Punycode
* string.
*/
var toUnicode = function(input) {
	return mapDomain(input, function(string) {
		return regexPunycode.test(string) ? decode(string.slice(4).toLowerCase()) : string;
	});
};
/**
* Converts a Unicode string representing a domain name or an email address to
* Punycode. Only the non-ASCII parts of the domain name will be converted,
* i.e. it doesn't matter if you call it with a domain that's already in
* ASCII.
* @memberOf punycode
* @param {String} input The domain name or email address to convert, as a
* Unicode string.
* @returns {String} The Punycode representation of the given domain name or
* email address.
*/
var toASCII = function(input) {
	return mapDomain(input, function(string) {
		return regexNonASCII.test(string) ? "xn--" + encode(string) : string;
	});
};
/** Define the public API */
var punycode = {
	/**
	* A string representing the current Punycode.js version number.
	* @memberOf punycode
	* @type String
	*/
	"version": "2.3.1",
	/**
	* An object of methods to convert from JavaScript's internal character
	* representation (UCS-2) to Unicode code points, and back.
	* @see <https://mathiasbynens.be/notes/javascript-encoding>
	* @memberOf punycode
	* @type Object
	*/
	"ucs2": {
		"decode": ucs2decode,
		"encode": ucs2encode
	},
	"decode": decode,
	"encode": encode,
	"toASCII": toASCII,
	"toUnicode": toUnicode
};
//#endregion
//#region node_modules/markdown-it/lib/index.mjs
var config = {
	default: {
		options: {
			html: false,
			xhtmlOut: false,
			breaks: false,
			langPrefix: "language-",
			linkify: false,
			typographer: false,
			quotes: "“”‘’",
			highlight: null,
			maxNesting: 100
		},
		components: {
			core: {},
			block: {},
			inline: {}
		}
	},
	zero: {
		options: {
			html: false,
			xhtmlOut: false,
			breaks: false,
			langPrefix: "language-",
			linkify: false,
			typographer: false,
			quotes: "“”‘’",
			highlight: null,
			maxNesting: 20
		},
		components: {
			core: { rules: [
				"normalize",
				"block",
				"inline",
				"text_join"
			] },
			block: { rules: ["paragraph"] },
			inline: {
				rules: ["text"],
				rules2: ["balance_pairs", "fragments_join"]
			}
		}
	},
	commonmark: {
		options: {
			html: true,
			xhtmlOut: true,
			breaks: false,
			langPrefix: "language-",
			linkify: false,
			typographer: false,
			quotes: "“”‘’",
			highlight: null,
			maxNesting: 20
		},
		components: {
			core: { rules: [
				"normalize",
				"block",
				"inline",
				"text_join"
			] },
			block: { rules: [
				"blockquote",
				"code",
				"fence",
				"heading",
				"hr",
				"html_block",
				"lheading",
				"list",
				"reference",
				"paragraph"
			] },
			inline: {
				rules: [
					"autolink",
					"backticks",
					"emphasis",
					"entity",
					"escape",
					"html_inline",
					"image",
					"link",
					"newline",
					"text"
				],
				rules2: [
					"balance_pairs",
					"emphasis",
					"fragments_join"
				]
			}
		}
	}
};
var BAD_PROTO_RE = /^(vbscript|javascript|file|data):/;
var GOOD_DATA_RE = /^data:image\/(gif|png|jpeg|webp);/;
function validateLink(url) {
	const str = url.trim().toLowerCase();
	return BAD_PROTO_RE.test(str) ? GOOD_DATA_RE.test(str) : true;
}
var RECODE_HOSTNAME_FOR = [
	"http:",
	"https:",
	"mailto:"
];
function normalizeLink(url) {
	const parsed = urlParse(url, true);
	if (parsed.hostname) {
		if (!parsed.protocol || RECODE_HOSTNAME_FOR.indexOf(parsed.protocol) >= 0) try {
			parsed.hostname = punycode.toASCII(parsed.hostname);
		} catch (er) {}
	}
	return encode$1(format(parsed));
}
function normalizeLinkText(url) {
	const parsed = urlParse(url, true);
	if (parsed.hostname) {
		if (!parsed.protocol || RECODE_HOSTNAME_FOR.indexOf(parsed.protocol) >= 0) try {
			parsed.hostname = punycode.toUnicode(parsed.hostname);
		} catch (er) {}
	}
	return decode$1(format(parsed), decode$1.defaultChars + "%");
}
/**
* class MarkdownIt
*
* Main parser/renderer class.
*
* ##### Usage
*
* ```javascript
* // node.js, "classic" way:
* var MarkdownIt = require('markdown-it'),
*     md = new MarkdownIt();
* var result = md.render('# markdown-it rulezz!');
*
* // node.js, the same, but with sugar:
* var md = require('markdown-it')();
* var result = md.render('# markdown-it rulezz!');
*
* // browser without AMD, added to "window" on script load
* // Note, there are no dash.
* var md = window.markdownit();
* var result = md.render('# markdown-it rulezz!');
* ```
*
* Single line rendering, without paragraph wrap:
*
* ```javascript
* var md = require('markdown-it')();
* var result = md.renderInline('__markdown-it__ rulezz!');
* ```
**/
/**
* new MarkdownIt([presetName, options])
* - presetName (String): optional, `commonmark` / `zero`
* - options (Object)
*
* Creates parser instanse with given config. Can be called without `new`.
*
* ##### presetName
*
* MarkdownIt provides named presets as a convenience to quickly
* enable/disable active syntax rules and options for common use cases.
*
* - ["commonmark"](https://github.com/markdown-it/markdown-it/blob/master/lib/presets/commonmark.mjs) -
*   configures parser to strict [CommonMark](http://commonmark.org/) mode.
* - [default](https://github.com/markdown-it/markdown-it/blob/master/lib/presets/default.mjs) -
*   similar to GFM, used when no preset name given. Enables all available rules,
*   but still without html, typographer & autolinker.
* - ["zero"](https://github.com/markdown-it/markdown-it/blob/master/lib/presets/zero.mjs) -
*   all rules disabled. Useful to quickly setup your config via `.enable()`.
*   For example, when you need only `bold` and `italic` markup and nothing else.
*
* ##### options:
*
* - __html__ - `false`. Set `true` to enable HTML tags in source. Be careful!
*   That's not safe! You may need external sanitizer to protect output from XSS.
*   It's better to extend features via plugins, instead of enabling HTML.
* - __xhtmlOut__ - `false`. Set `true` to add '/' when closing single tags
*   (`<br />`). This is needed only for full CommonMark compatibility. In real
*   world you will need HTML output.
* - __breaks__ - `false`. Set `true` to convert `\n` in paragraphs into `<br>`.
* - __langPrefix__ - `language-`. CSS language class prefix for fenced blocks.
*   Can be useful for external highlighters.
* - __linkify__ - `false`. Set `true` to autoconvert URL-like text to links.
* - __typographer__  - `false`. Set `true` to enable [some language-neutral
*   replacement](https://github.com/markdown-it/markdown-it/blob/master/lib/rules_core/replacements.mjs) +
*   quotes beautification (smartquotes).
* - __quotes__ - `“”‘’`, String or Array. Double + single quotes replacement
*   pairs, when typographer enabled and smartquotes on. For example, you can
*   use `'«»„“'` for Russian, `'„“‚‘'` for German, and
*   `['«\xA0', '\xA0»', '‹\xA0', '\xA0›']` for French (including nbsp).
* - __highlight__ - `null`. Highlighter function for fenced code blocks.
*   Highlighter `function (str, lang)` should return escaped HTML. It can also
*   return empty string if the source was not changed and should be escaped
*   externaly. If result starts with <pre... internal wrapper is skipped.
*
* ##### Example
*
* ```javascript
* // commonmark mode
* var md = require('markdown-it')('commonmark');
*
* // default mode
* var md = require('markdown-it')();
*
* // enable everything
* var md = require('markdown-it')({
*   html: true,
*   linkify: true,
*   typographer: true
* });
* ```
*
* ##### Syntax highlighting
*
* ```js
* var hljs = require('highlight.js') // https://highlightjs.org/
*
* var md = require('markdown-it')({
*   highlight: function (str, lang) {
*     if (lang && hljs.getLanguage(lang)) {
*       try {
*         return hljs.highlight(str, { language: lang, ignoreIllegals: true }).value;
*       } catch (__) {}
*     }
*
*     return ''; // use external default escaping
*   }
* });
* ```
*
* Or with full wrapper override (if you need assign class to `<pre>` or `<code>`):
*
* ```javascript
* var hljs = require('highlight.js') // https://highlightjs.org/
*
* // Actual default values
* var md = require('markdown-it')({
*   highlight: function (str, lang) {
*     if (lang && hljs.getLanguage(lang)) {
*       try {
*         return '<pre><code class="hljs">' +
*                hljs.highlight(str, { language: lang, ignoreIllegals: true }).value +
*                '</code></pre>';
*       } catch (__) {}
*     }
*
*     return '<pre><code class="hljs">' + md.utils.escapeHtml(str) + '</code></pre>';
*   }
* });
* ```
*
**/
function MarkdownIt(presetName, options) {
	if (!(this instanceof MarkdownIt)) return new MarkdownIt(presetName, options);
	if (!options) {
		if (!isString$1(presetName)) {
			options = presetName || {};
			presetName = "default";
		}
	}
	/**
	* MarkdownIt#inline -> ParserInline
	*
	* Instance of [[ParserInline]]. You may need it to add new rules when
	* writing plugins. For simple rules control use [[MarkdownIt.disable]] and
	* [[MarkdownIt.enable]].
	**/
	this.inline = new ParserInline();
	/**
	* MarkdownIt#block -> ParserBlock
	*
	* Instance of [[ParserBlock]]. You may need it to add new rules when
	* writing plugins. For simple rules control use [[MarkdownIt.disable]] and
	* [[MarkdownIt.enable]].
	**/
	this.block = new ParserBlock();
	/**
	* MarkdownIt#core -> Core
	*
	* Instance of [[Core]] chain executor. You may need it to add new rules when
	* writing plugins. For simple rules control use [[MarkdownIt.disable]] and
	* [[MarkdownIt.enable]].
	**/
	this.core = new Core();
	/**
	* MarkdownIt#renderer -> Renderer
	*
	* Instance of [[Renderer]]. Use it to modify output look. Or to add rendering
	* rules for new token types, generated by plugins.
	*
	* ##### Example
	*
	* ```javascript
	* var md = require('markdown-it')();
	*
	* function myToken(tokens, idx, options, env, self) {
	*   //...
	*   return result;
	* };
	*
	* md.renderer.rules['my_token'] = myToken
	* ```
	*
	* See [[Renderer]] docs and [source code](https://github.com/markdown-it/markdown-it/blob/master/lib/renderer.mjs).
	**/
	this.renderer = new Renderer();
	/**
	* MarkdownIt#linkify -> LinkifyIt
	*
	* [linkify-it](https://github.com/markdown-it/linkify-it) instance.
	* Used by [linkify](https://github.com/markdown-it/markdown-it/blob/master/lib/rules_core/linkify.mjs)
	* rule.
	**/
	this.linkify = new LinkifyIt();
	/**
	* MarkdownIt#validateLink(url) -> Boolean
	*
	* Link validation function. CommonMark allows too much in links. By default
	* we disable `javascript:`, `vbscript:`, `file:` schemas, and almost all `data:...` schemas
	* except some embedded image types.
	*
	* You can change this behaviour:
	*
	* ```javascript
	* var md = require('markdown-it')();
	* // enable everything
	* md.validateLink = function () { return true; }
	* ```
	**/
	this.validateLink = validateLink;
	/**
	* MarkdownIt#normalizeLink(url) -> String
	*
	* Function used to encode link url to a machine-readable format,
	* which includes url-encoding, punycode, etc.
	**/
	this.normalizeLink = normalizeLink;
	/**
	* MarkdownIt#normalizeLinkText(url) -> String
	*
	* Function used to decode link url to a human-readable format`
	**/
	this.normalizeLinkText = normalizeLinkText;
	/**
	* MarkdownIt#utils -> utils
	*
	* Assorted utility functions, useful to write plugins. See details
	* [here](https://github.com/markdown-it/markdown-it/blob/master/lib/common/utils.mjs).
	**/
	this.utils = utils_exports;
	/**
	* MarkdownIt#helpers -> helpers
	*
	* Link components parser functions, useful to write plugins. See details
	* [here](https://github.com/markdown-it/markdown-it/blob/master/lib/helpers).
	**/
	this.helpers = assign$1({}, helpers_exports);
	this.options = {};
	this.configure(presetName);
	if (options) this.set(options);
}
/** chainable
* MarkdownIt.set(options)
*
* Set parser options (in the same format as in constructor). Probably, you
* will never need it, but you can change options after constructor call.
*
* ##### Example
*
* ```javascript
* var md = require('markdown-it')()
*             .set({ html: true, breaks: true })
*             .set({ typographer: true });
* ```
*
* __Note:__ To achieve the best possible performance, don't modify a
* `markdown-it` instance options on the fly. If you need multiple configurations
* it's best to create multiple instances and initialize each with separate
* config.
**/
MarkdownIt.prototype.set = function(options) {
	assign$1(this.options, options);
	return this;
};
/** chainable, internal
* MarkdownIt.configure(presets)
*
* Batch load of all options and compenent settings. This is internal method,
* and you probably will not need it. But if you will - see available presets
* and data structure [here](https://github.com/markdown-it/markdown-it/tree/master/lib/presets)
*
* We strongly recommend to use presets instead of direct config loads. That
* will give better compatibility with next versions.
**/
MarkdownIt.prototype.configure = function(presets) {
	const self = this;
	if (isString$1(presets)) {
		const presetName = presets;
		presets = config[presetName];
		if (!presets) throw new Error("Wrong `markdown-it` preset \"" + presetName + "\", check name");
	}
	if (!presets) throw new Error("Wrong `markdown-it` preset, can't be empty");
	if (presets.options) self.set(presets.options);
	if (presets.components) Object.keys(presets.components).forEach(function(name) {
		if (presets.components[name].rules) self[name].ruler.enableOnly(presets.components[name].rules);
		if (presets.components[name].rules2) self[name].ruler2.enableOnly(presets.components[name].rules2);
	});
	return this;
};
/** chainable
* MarkdownIt.enable(list, ignoreInvalid)
* - list (String|Array): rule name or list of rule names to enable
* - ignoreInvalid (Boolean): set `true` to ignore errors when rule not found.
*
* Enable list or rules. It will automatically find appropriate components,
* containing rules with given names. If rule not found, and `ignoreInvalid`
* not set - throws exception.
*
* ##### Example
*
* ```javascript
* var md = require('markdown-it')()
*             .enable(['sub', 'sup'])
*             .disable('smartquotes');
* ```
**/
MarkdownIt.prototype.enable = function(list, ignoreInvalid) {
	let result = [];
	if (!Array.isArray(list)) list = [list];
	[
		"core",
		"block",
		"inline"
	].forEach(function(chain) {
		result = result.concat(this[chain].ruler.enable(list, true));
	}, this);
	result = result.concat(this.inline.ruler2.enable(list, true));
	const missed = list.filter(function(name) {
		return result.indexOf(name) < 0;
	});
	if (missed.length && !ignoreInvalid) throw new Error("MarkdownIt. Failed to enable unknown rule(s): " + missed);
	return this;
};
/** chainable
* MarkdownIt.disable(list, ignoreInvalid)
* - list (String|Array): rule name or list of rule names to disable.
* - ignoreInvalid (Boolean): set `true` to ignore errors when rule not found.
*
* The same as [[MarkdownIt.enable]], but turn specified rules off.
**/
MarkdownIt.prototype.disable = function(list, ignoreInvalid) {
	let result = [];
	if (!Array.isArray(list)) list = [list];
	[
		"core",
		"block",
		"inline"
	].forEach(function(chain) {
		result = result.concat(this[chain].ruler.disable(list, true));
	}, this);
	result = result.concat(this.inline.ruler2.disable(list, true));
	const missed = list.filter(function(name) {
		return result.indexOf(name) < 0;
	});
	if (missed.length && !ignoreInvalid) throw new Error("MarkdownIt. Failed to disable unknown rule(s): " + missed);
	return this;
};
/** chainable
* MarkdownIt.use(plugin, params)
*
* Load specified plugin with given params into current parser instance.
* It's just a sugar to call `plugin(md, params)` with curring.
*
* ##### Example
*
* ```javascript
* var iterator = require('markdown-it-for-inline');
* var md = require('markdown-it')()
*             .use(iterator, 'foo_replace', 'text', function (tokens, idx) {
*               tokens[idx].content = tokens[idx].content.replace(/foo/g, 'bar');
*             });
* ```
**/
MarkdownIt.prototype.use = function(plugin) {
	const args = [this].concat(Array.prototype.slice.call(arguments, 1));
	plugin.apply(plugin, args);
	return this;
};
/** internal
* MarkdownIt.parse(src, env) -> Array
* - src (String): source string
* - env (Object): environment sandbox
*
* Parse input string and return list of block tokens (special token type
* "inline" will contain list of inline tokens). You should not call this
* method directly, until you write custom renderer (for example, to produce
* AST).
*
* `env` is used to pass data between "distributed" rules and return additional
* metadata like reference info, needed for the renderer. It also can be used to
* inject data in specific cases. Usually, you will be ok to pass `{}`,
* and then pass updated object to renderer.
**/
MarkdownIt.prototype.parse = function(src, env) {
	if (typeof src !== "string") throw new Error("Input data should be a String");
	const state = new this.core.State(src, this, env);
	this.core.process(state);
	return state.tokens;
};
/**
* MarkdownIt.render(src [, env]) -> String
* - src (String): source string
* - env (Object): environment sandbox
*
* Render markdown string into html. It does all magic for you :).
*
* `env` can be used to inject additional metadata (`{}` by default).
* But you will not need it with high probability. See also comment
* in [[MarkdownIt.parse]].
**/
MarkdownIt.prototype.render = function(src, env) {
	env = env || {};
	return this.renderer.render(this.parse(src, env), this.options, env);
};
/** internal
* MarkdownIt.parseInline(src, env) -> Array
* - src (String): source string
* - env (Object): environment sandbox
*
* The same as [[MarkdownIt.parse]] but skip all block rules. It returns the
* block tokens list with the single `inline` element, containing parsed inline
* tokens in `children` property. Also updates `env` object.
**/
MarkdownIt.prototype.parseInline = function(src, env) {
	const state = new this.core.State(src, this, env);
	state.inlineMode = true;
	this.core.process(state);
	return state.tokens;
};
/**
* MarkdownIt.renderInline(src [, env]) -> String
* - src (String): source string
* - env (Object): environment sandbox
*
* Similar to [[MarkdownIt.render]] but for single paragraph content. Result
* will NOT be wrapped into `<p>` tags.
**/
MarkdownIt.prototype.renderInline = function(src, env) {
	env = env || {};
	return this.renderer.render(this.parseInline(src, env), this.options, env);
};
//#endregion
//#region web/src/markdown.js
var md = new MarkdownIt({
	html: false,
	linkify: true,
	breaks: true
});
md.linkify.set({
	fuzzyLink: false,
	fuzzyEmail: false
});
md.disable("image");
var renderLinkOpen = md.renderer.rules.link_open || ((tokens, i, options, env, self) => self.renderToken(tokens, i, options));
md.renderer.rules.link_open = (tokens, i, options, env, self) => {
	tokens[i].attrSet("target", "_blank");
	tokens[i].attrSet("rel", "noopener noreferrer");
	return renderLinkOpen(tokens, i, options, env, self);
};
var cache = /* @__PURE__ */ new Map();
var CACHE_LIMIT = 1e3;
function renderMarkdown(text) {
	const source = text || "";
	let out = cache.get(source);
	if (out === void 0) {
		out = md.render(source);
		if (cache.size >= CACHE_LIMIT) cache.delete(cache.keys().next().value);
		cache.set(source, out);
	}
	return out;
}
//#endregion
//#region web/src/teammates.js
function teammates(recipients, teams, user) {
	const me = recipients.find((r) => r.user_id === user);
	const team = me && (teams || []).find((t) => t.id === me.team_id);
	if (!team) return null;
	return {
		team,
		members: recipients.filter((r) => r.team_id === team.id && (r.pane_alive || r.user_id === user)).sort((a, b) => (b.user_id === team.queen) - (a.user_id === team.queen) || a.user_id.localeCompare(b.user_id))
	};
}
function stepTeammate(members, user, by) {
	const ids = members.map((m) => m.user_id);
	if (ids.length < 2) return null;
	return ids[(Math.max(0, ids.indexOf(user)) + by + ids.length) % ids.length];
}
//#endregion
//#region web/src/newlines.js
function shellNewlines(text) {
	if (!text || text.includes("\n") || !text.includes("\\n")) return text;
	return text.split(/(`[^`]*`)/).map((part, i) => i % 2 ? part : part.replace(/(?<!\\)\\n/g, "\n")).join("");
}
//#endregion
//#region web/src/chats.js
function ownerChats(messages, query = "") {
	const words = query.toLowerCase().split(/\s+/).filter(Boolean);
	const seen = /* @__PURE__ */ new Set();
	const byAgent = /* @__PURE__ */ new Map();
	for (const m of messages) {
		if (seen.has(m.id) || m.sender !== "owner" && m.recipient !== "owner") continue;
		if (m.sender === "owner" && m.recipient === "owner") continue;
		seen.add(m.id);
		const agent = m.sender === "owner" ? m.recipient : m.sender;
		const chat = byAgent.get(agent) || {
			agent,
			last: null,
			count: 0,
			match: null,
			matches: 0
		};
		chat.count += 1;
		if (!chat.last || m.ts > chat.last.ts) chat.last = m;
		if (words.length) {
			const text = `${m.context || ""} ${m.content || ""}`.toLowerCase();
			if (words.every((w) => text.includes(w))) {
				chat.matches += 1;
				if (!chat.match || m.ts > chat.match.ts) chat.match = m;
			}
		}
		byAgent.set(agent, chat);
	}
	return [...byAgent.values()].filter((c) => !words.length || c.matches > 0).sort((a, b) => words.length ? b.match.ts - a.match.ts : b.last.ts - a.last.ts);
}
//#endregion
//#region web/src/main.js
function JumpToPane({ r }) {
	const [copied, setCopied] = d(false);
	if (!(r.pane_alive || (r.offline_reason || "").includes("bare shell")) || !String(r.tmux_pane).startsWith("%")) return null;
	const command = `switch-client -t ${r.tmux_pane}`;
	const copy = async (e) => {
		e.stopPropagation();
		try {
			await navigator.clipboard.writeText(command);
			setCopied(true);
			setTimeout(() => setCopied(false), 1500);
		} catch {
			prompt("Copy this, then paste it at tmux's command prompt (prefix, then :)", command);
		}
	};
	return m$1`<span class="jump-cmd" title=${`Copy "${command}" — paste it at tmux's command prompt (prefix, then :) to jump to ${r.pane_label}`}>
    <span class="sep">· </span><code>${command}</code>
    <button type="button" class="mini" onClick=${copy}>${copied ? "copied" : "copy"}</button>
  </span>`;
}
function CompactButton({ r }) {
	const [busy, setBusy] = d(false);
	if (!r.pane_alive || !r.compact_command) return null;
	const compact = async () => {
		if (!confirm(`Compact ${r.user_id}'s context? This types ${r.compact_command} into its pane.`)) return;
		setBusy(true);
		const res = await typeInto(r.user_id, { text: r.compact_command });
		setBusy(false);
		if (!res.ok) alert(`Could not compact ${r.user_id}: ${await failure(res)}`);
	};
	return m$1`<button type="button" class="mini" disabled=${busy}
    title=${`Type ${r.compact_command} into ${r.user_id}'s pane to compact its context`}
    onClick=${compact}>${busy ? "compacting…" : "compact"}</button>`;
}
async function stopAgent(r, state, focusUser, refresh) {
	if (!confirm(`Stop ${r.user_id} on ${machineName(r.node)}? This kills its tmux pane and ends the running session. Messages and tasks are kept.`)) return;
	if ((await fetch(`/agents/${encodeURIComponent(r.user_id)}/stop`, { method: "POST" }).catch(() => null))?.ok) {
		if (focusUser === r.user_id) {
			const next = state.recipients.find((x) => x.pane_alive && x.user_id !== r.user_id);
			location.hash = next ? focusHash(next.user_id) : "#/";
		}
	} else alert(`Could not stop ${r.user_id}. Check its status before trying again.`);
	refresh();
}
async function retireAgents(ids, refresh) {
	const names = ids.length > 6 ? `${ids.slice(0, 6).join(", ")} and ${ids.length - 6} more` : ids.join(", ");
	if (!ids.length || !confirm(`Retire ${names}? ${ids.length > 1 ? "They leave" : "It leaves"} the dashboard and ${ids.length > 1 ? "their teams" : "its team"}. Messages and tasks are kept.`)) return null;
	try {
		const response = await fetch("/recipients/retire", {
			method: "POST",
			headers: JSONH,
			body: JSON.stringify({ user_ids: ids })
		});
		const body = await response.json().catch(() => null);
		if (!response.ok || !body?.ok) {
			alert("Could not retire. Try again.");
			return null;
		}
		if (body.kept_live.length) alert(`Still running, so not retired: ${body.kept_live.join(", ")}`);
		return body;
	} catch {
		alert("Could not retire. Try again.");
		return null;
	} finally {
		refresh();
	}
}
function RetireButton({ ids, refresh, label, onDone = () => {} }) {
	const [busy, setBusy] = d(false);
	return m$1`<button type="button" class="mini retire" disabled=${busy || !ids.length} onClick=${async (e) => {
		e.preventDefault();
		e.stopPropagation();
		setBusy(true);
		const body = await retireAgents(ids, refresh);
		setBusy(false);
		if (body?.retired.length) onDone(body);
	}}>${busy ? "retiring…" : label}</button>`;
}
function StopAgentButton({ r, refresh }) {
	const [busy, setBusy] = d(false);
	const [message, setMessage] = d("");
	const stop = async () => {
		if (busy || !confirm(`Stop ${r.user_id} on ${machineName(r.node)}? This kills its tmux pane and ends the running session. Messages and tasks are kept.`)) return;
		setBusy(true);
		setMessage("");
		try {
			const response = await fetch(`/agents/${encodeURIComponent(r.user_id)}/stop`, { method: "POST" });
			const body = await response.json().catch(() => null);
			if (response.ok && body?.ok === true) setMessage(body.already_stopped ? "Already stopped." : "Agent stopped. Messages and tasks are kept.");
			else if (body?.detail?.status === "unknown" || !body?.detail?.error) setMessage("Stop not confirmed. Check the agent's status before retrying.");
			else setMessage(`Could not stop agent: ${body.detail.error}${body.detail.detail ? ` — ${body.detail.detail}` : ""}`);
		} catch {
			setMessage("Stop not confirmed. Check the agent's status before retrying.");
		} finally {
			setBusy(false);
			refresh();
		}
	};
	return m$1`<span class="agent-stop-control">
    ${r.pane_alive ? m$1`<button type="button" class="mini stop-agent" disabled=${busy} onClick=${stop}>
          ${busy ? "stopping…" : "stop agent"}</button>` : m$1`<${RetireButton} ids=${[r.user_id]} refresh=${refresh} label="retire agent" onDone=${() => {
		location.hash = "#/";
	}} />`}
    ${message && m$1`<span role="status"> ${message}</span>`}
  </span>`;
}
function ModelLabel({ r, refresh }) {
	const [editing, setEditing] = d(false);
	const [value, setValue] = d("");
	const [known, setKnown] = d([]);
	const [busy, setBusy] = d(false);
	const inputRef = A(null);
	h(() => {
		if (editing) inputRef.current?.focus();
	}, [editing]);
	const flavor = (r.flavor || "generic").toLowerCase();
	const listId = `models-${r.user_id}`;
	const start = () => {
		setValue(r.model || "");
		setEditing(true);
		fetch("/api/spawn-options").then((res) => res.json()).then((d) => setKnown(((d.harnesses || []).find((h) => h.flavor === flavor) || {}).models || [])).catch(() => {});
	};
	const save = async () => {
		if (busy) return;
		if (value.trim() === (r.model || "")) {
			setEditing(false);
			return;
		}
		setBusy(true);
		const res = await fetch(`/agents/${encodeURIComponent(r.user_id)}/model`, {
			method: "POST",
			headers: JSONH,
			body: JSON.stringify({ model: value })
		});
		setBusy(false);
		if (!res.ok) {
			alert(`Could not update the model label for ${r.user_id}.`);
			return;
		}
		setEditing(false);
		refresh();
	};
	if (!editing) return m$1`<button type="button" class="model-label" onClick=${start}
      title="Edit the model label. Display only: switch the real model in the agent's pane, then update it here.">
      ${r.model ? m$1`<b>${r.model}</b>` : m$1`<span class="unset">set model</span>`} <span class="pen">✎</span>
    </button>`;
	return m$1`<span class="model-edit">
    <input type="text" value=${value} list=${listId} placeholder="e.g. claude-opus-4-7"
      aria-label=${`Model label for ${r.user_id}`} disabled=${busy} ref=${inputRef}
      onInput=${(e) => setValue(e.target.value)}
      onKeyDown=${(e) => {
		if (e.key === "Enter") {
			e.preventDefault();
			save();
		}
		if (e.key === "Escape") setEditing(false);
	}} />
    <datalist id=${listId}>${known.map((m) => m$1`<option key=${m} value=${m} />`)}</datalist>
    <button type="button" class="mini" disabled=${busy} onClick=${save}>${busy ? "saving…" : "save"}</button>
    <button type="button" class="mini" disabled=${busy} onClick=${() => setEditing(false)}>cancel</button>
  </span>`;
}
var DEFAULT_MODEL = "default";
function SpawnControl({ refresh, nodes }) {
	const [harnesses, setHarnesses] = d([]);
	const [node, setNode] = d("");
	const [flavor, setFlavor] = d("claude");
	const [model, setModel] = d(DEFAULT_MODEL);
	const [busy, setBusy] = d(false);
	const [err, setErr] = d("");
	h(() => {
		let live = true;
		fetch("/api/spawn-options").then((r) => r.json()).then((d) => {
			if (live && d.harnesses) setHarnesses(d.harnesses);
		}).catch(() => {});
		return () => {
			live = false;
		};
	}, []);
	const target = spawnTarget(nodes, node, harnesses);
	const offered = target.harnesses || [];
	const models = (offered.find((h) => h.flavor === flavor) || {}).models || [];
	const pickFlavor = (f) => {
		setFlavor(f);
		setModel(DEFAULT_MODEL);
	};
	const pickNode = (n) => {
		setNode(n);
		const next = spawnTarget(nodes, n, harnesses);
		if (next.ok && next.harnesses.length && !next.harnesses.some((h) => h.flavor === flavor)) pickFlavor(next.harnesses[0].flavor);
	};
	const enrolled = nodes || [];
	const choices = enrolled.some((n) => n.name === node) || !node ? enrolled : enrolled.concat([{
		name: node,
		connected: false,
		gone: true
	}]);
	const spawn = async (e) => {
		e.preventDefault();
		if (!target.ok) {
			setErr(target.reason);
			return;
		}
		setBusy(true);
		setErr("");
		const body = {
			flavor,
			model: model === DEFAULT_MODEL ? null : model
		};
		if (target.remote) body.node = target.node;
		try {
			const r = await fetch("/agents/spawn", {
				method: "POST",
				headers: JSONH,
				body: JSON.stringify(body)
			});
			let payload = null;
			try {
				payload = await r.json();
			} catch {
				payload = null;
			}
			const outcome = spawnOutcome(r.ok, payload);
			if (outcome.status === "failed") setErr(`spawn failed: ${outcome.reason}`);
			else if (outcome.status === "unknown") setErr(`spawn outcome unknown: ${outcome.reason}${outcome.user ? ` (registered as ${outcome.user})` : ""}`);
			else if (outcome.status === "uncertain") setErr(`spawn not confirmed: ${outcome.reason}; check the agents list`);
		} catch (err) {
			setErr(`not confirmed: ${unansweredOutcome(err).reason}`);
		} finally {
			setBusy(false);
			refresh();
		}
	};
	const flavors = offered.length ? offered.map((h) => h.flavor) : [];
	return m$1`<form class="spawn" onSubmit=${spawn}>
    <div class="spawn-heading">Spawn agent · choose destination</div>
    ${(enrolled.length > 1 || node) && m$1`<select title="machine" value=${node} onChange=${(e) => pickNode(e.target.value)}>
      ${choices.map((n) => m$1`<option key=${n.name} value=${n.local ? "" : n.name} disabled=${!n.local && !n.connected}>${n.local ? `${n.name} (hub)` : n.gone ? `${n.name} (no longer enrolled)` : n.connected ? n.name : `${n.name} (not connected)`}</option>`)}
    </select>`}
    ${!target.ok && m$1`<span class="spawn-note">${target.reason}. Pick a connected machine.</span>`}
    <select title="harness" value=${flavor} onChange=${(e) => pickFlavor(e.target.value)} disabled=${!target.ok}>
      ${flavors.map((f) => m$1`<option key=${f} value=${f}>${f}</option>`)}
    </select>
    <select title="model" value=${model} onChange=${(e) => setModel(e.target.value)}
      disabled=${models.length === 0}>
      <option value=${DEFAULT_MODEL}>default model</option>
      ${models.map((m) => m$1`<option key=${m} value=${m}>${m}</option>`)}
    </select>
    <button class="act" type="submit" disabled=${busy || !target.ok}>${busy ? "spawning…" : "spawn agent"}</button>
    ${err && m$1`<span style="color:var(--alert); font-size:11px">${err}</span>`}
  </form>`;
}
var AGENT_DRAG_TYPE = "application/x-agent-swarm-agent";
async function moveAgentToTeam(user, teamId, refresh) {
	await fetch(`/agents/${encodeURIComponent(user)}/team`, {
		method: "POST",
		headers: JSONH,
		body: JSON.stringify({ team_id: teamId })
	});
	refresh();
}
function agentDropProps(setOver, onDropUser) {
	return {
		onDragOver: (e) => {
			if (![...e.dataTransfer.types].includes(AGENT_DRAG_TYPE)) return;
			e.preventDefault();
			e.dataTransfer.dropEffect = "move";
			setOver(true);
		},
		onDragLeave: (e) => {
			if (!e.currentTarget.contains(e.relatedTarget)) setOver(false);
		},
		onDrop: (e) => {
			e.preventDefault();
			setOver(false);
			const user = e.dataTransfer.getData(AGENT_DRAG_TYPE);
			if (user) onDropUser(user);
		}
	};
}
function NewTeam({ refresh }) {
	const [name, setName] = d("");
	const create = async (e) => {
		e.preventDefault();
		if (!name.trim()) return;
		await fetch("/teams", {
			method: "POST",
			headers: JSONH,
			body: JSON.stringify({ name: name.trim() })
		});
		setName("");
		refresh();
	};
	return m$1`<form class="newteam" onSubmit=${create}>
    <input type="text" placeholder="team name" value=${name}
      onInput=${(e) => setName(e.target.value)} />
    <button class="act" type="submit">new team</button>
  </form>`;
}
function Resend({ m, refresh }) {
	const [busy, setBusy] = d(false);
	const [note, setNote] = d("");
	const resend = async () => {
		if (!window.confirm("The outcome of this message is unknown: the agent may already have it. Send it again as a new message?")) return;
		setBusy(true);
		setNote("");
		try {
			const r = await fetch("/owner/send", {
				method: "POST",
				headers: JSONH,
				body: JSON.stringify({
					recipient: m.recipient,
					content: m.content,
					context: m.context,
					attachments: m.attachments || []
				})
			});
			let body = null;
			try {
				body = await r.json();
			} catch {
				body = null;
			}
			const outcome = deliveryOutcome(r.ok, body);
			if (outcome.status !== "delivered") setNote(`${outcome.status}: ${outcome.reason}`);
		} catch (err) {
			setNote(`not confirmed: ${unansweredOutcome(err).reason}`);
		} finally {
			setBusy(false);
			refresh();
		}
	};
	return m$1`<button type="button" class="resend" disabled=${busy} onClick=${resend}
    title="Send this message again as a new message">${busy ? "sending…" : "send again"}</button>${note && m$1` <span class="ctx">${note}</span>`}`;
}
function MachineBar({ state, machine, selectMachine }) {
	const machines = machineList(state.nodes, state.recipients);
	return m$1`<section class="machine-bar" aria-label="Machine selector">
    <div class="machine-heading"><span>Machines</span><small>Color identifies the machine</small></div>
    <div class="machine-choices">
      <button class=${`machine-choice all ${machine === null ? "active" : ""}`} aria-pressed=${machine === null}
        onClick=${() => selectMachine(null)}><strong>All machines</strong><span>${machines.length} machines · ${state.recipients.filter((r) => r.pane_alive).length} live agents</span></button>
      ${machines.map((n) => m$1`<button key=${n.name} class=${`machine-choice ${machine === n.name ? "active" : ""} ${n.connected ? "" : "disconnected"}`}
          style=${`--machine:${machineColor(n.name)}`} aria-pressed=${machine === n.name}
          onClick=${() => selectMachine(machine === n.name ? null : n.name)}>
        <strong><span class="machine-mark" aria-hidden="true"></span>${n.name}${n.local && m$1`<small>hub</small>`}</strong>
        <span>${n.connected ? "Connected" : n.missing ? "Not enrolled" : "Disconnected"} · ${n.live} live${n.total > n.live ? ` / ${n.total} registered` : " agents"}</span>
      </button>`)}
    </div>
    ${machine !== null && m$1`<div class="machine-filter-note">Highlighting bees and showing agents on <b>${machine}</b>. Task board shows all machines. <button onClick=${() => selectMachine(null)}>Clear filter ×</button></div>`}
  </section>`;
}
function TaskCard({ t, agentIds, teams, blockers, refresh }) {
	const [dragging, setDragging] = d(false);
	const [showNote, setShowNote] = d(false);
	const [err, setErr] = d("");
	const when = (/* @__PURE__ */ new Date(t.created_at * 1e3)).toLocaleTimeString([], {
		hour: "2-digit",
		minute: "2-digit"
	});
	const ids = t.assignee && !agentIds.includes(t.assignee) ? agentIds.concat(t.assignee) : agentIds;
	const act = async (p) => {
		const r = await patchTask(t.id, p);
		if (!r.ok) {
			setErr(r.error);
			return false;
		}
		setErr("");
		refresh();
		return true;
	};
	const draggable = t.status !== "done";
	const blocked = blockers.length > 0 && t.status !== "done";
	const deps = t.depends_on || [];
	const dragStart = (e) => {
		if (!draggable) return;
		e.dataTransfer.effectAllowed = "move";
		e.dataTransfer.setData("application/x-agent-swarm-task", String(t.id));
		e.dataTransfer.setData("text/plain", String(t.id));
		setDragging(true);
	};
	const onAssign = (e) => {
		const v = e.target.value;
		if (v.startsWith("t:")) act({ team_id: Number(v.slice(2)) });
		else if (v) act({ assignee: v });
		else act({
			assignee: null,
			team_id: null
		});
	};
	return m$1`<div class=${`tcard ${dragging ? "dragging" : ""} ${blocked ? "blocked" : ""}`} draggable=${draggable}
      onDragStart=${dragStart} onDragEnd=${() => setDragging(false)}
      title=${draggable ? "Drag this task onto a bee or team in the activity view to assign it" : "Reopen this task before assigning it by drag"}>
    <div class="t">${t.title}</div>
    <div class="meta">#${t.id} · created ${when}${deps.length > 0 ? ` · after ${deps.map((d) => `#${d}`).join(" ")}` : ""}${t.description ? ` · ${t.description}` : ""}${t.worktree ? ` · worktree ${t.worktree}` : ""}</div>
    ${blocked && m$1`<div class="meta blocked-tag" title="dependencies not yet done">blocked by ${blockers.map((d) => `#${d}`).join(" ")}</div>`}
    <${AttachmentList} files=${t.attachments} />
    ${t.assignee && m$1`<div class="meta">${t.status === "open" ? "assigned to" : t.status === "done" ? "done by" : "picked up by"} <a class="agent-link" href=${focusHash(t.assignee)}
        title=${`Open ${t.assignee} and message it`}>${t.assignee}</a></div>`}
    ${t.note && m$1`<div class="tnote">
      <button type="button" class="tnote-toggle" onClick=${() => setShowNote(!showNote)}
        title="How to verify this work">${showNote ? "▾" : "▸"} how to verify</button>
      ${showNote && m$1`<div class="tnote-body">${t.note}</div>`}
    </div>`}
    ${err && m$1`<div class="meta tnote-err">${err}</div>`}
    <div class="foot">
      <${TaskTrash} task=${t} refresh=${refresh} />
      <select title="assignee" aria-label=${`Assign task #${t.id}`} disabled=${t.status === "done"}
        value=${t.team_id ? `t:${t.team_id}` : t.assignee || ""}
        onChange=${onAssign}>
        <option value="">unassigned</option>
        ${teams.length > 0 && m$1`<optgroup label="teams">
          ${teams.map((x) => m$1`<option key=${`t:${x.id}`} value=${`t:${x.id}`}>team ${x.name}</option>`)}
        </optgroup>`}
        ${ids.map((a) => m$1`<option key=${a} value=${a}>${a}${agentIds.includes(a) ? "" : " (stopped)"}</option>`)}
      </select>
      <${TaskStatusActions} task=${t} refresh=${refresh} />
    </div>
  </div>`;
}
var DONE_ON_BOARD = 10;
function TaskComposer({ state, refresh, user = "", folded = false }) {
	const draftKey = `agent-swarm:task-draft:${user || "board"}`;
	const [draft] = d(() => {
		try {
			return JSON.parse(localStorage.getItem(draftKey) || "null") || {};
		} catch {
			return {};
		}
	});
	const [title, setTitle] = d(draft.title || "");
	const [description, setDescription] = d(draft.description || "");
	const [assignee, setAssignee] = d(draft.assignee ?? user);
	const [files, setFiles] = d(Array.isArray(draft.files) ? draft.files.filter((f) => typeof f === "string") : []);
	const [status, setStatus] = d("");
	const [busy, setBusy] = d(false);
	const attachments = useAttachments(files, setFiles, setStatus, draftKey);
	h(() => {
		try {
			if (title || description || files.length) localStorage.setItem(draftKey, JSON.stringify({
				title,
				description,
				assignee,
				files
			}));
			else localStorage.removeItem(draftKey);
		} catch {}
	}, [
		draftKey,
		title,
		description,
		assignee,
		files
	]);
	const agents = state.recipients.filter((r) => r.pane_alive || r.user_id === user || r.user_id === assignee);
	const teams = state.teams || [];
	const targetExists = !assignee || (assignee.startsWith("t:") ? teams.some((t) => `t:${t.id}` === assignee) : agents.some((r) => r.user_id === assignee));
	const create = async (e) => {
		e.preventDefault();
		if (busy || attachments.uploading || !title.trim() || !targetExists) return;
		setBusy(true);
		setStatus("Creating task…");
		const body = {
			title: title.trim(),
			description: description.trim() || null,
			attachments: files
		};
		if (assignee.startsWith("t:")) body.team_id = Number(assignee.slice(2));
		else if (assignee) body.assignee = assignee;
		try {
			const response = await fetch("/tasks", {
				method: "POST",
				headers: JSONH,
				body: JSON.stringify(body)
			});
			const result = await response.json().catch(() => null);
			if (!response.ok || !result?.task?.id) {
				setStatus(result?.detail?.error ? `Task not created: ${result.detail.error}. Draft kept.` : "Creation not confirmed. Check the board before retrying; draft kept.");
				return;
			}
			setTitle("");
			setDescription("");
			setFiles([]);
			setStatus(`Created task #${result.task.id}${result.task.assignee ? ` · assigned to ${result.task.assignee}` : result.task.team_id ? " · assigned to team" : " · unassigned"}.`);
			await refresh();
		} catch {
			setStatus("Creation not confirmed. Check the board before retrying; draft kept.");
		} finally {
			setBusy(false);
		}
	};
	const form = m$1`<form class=${`task-composer ${attachments.dragging ? "dragging" : ""}`} onSubmit=${create} ...${busy ? {} : attachments.dropProps}>
    ${!folded && m$1`<div class="task-compose-heading">${user ? `Create a task for ${user}` : "New task"}</div>`}
    <input class="task-title" aria-label="Task title" placeholder="What needs doing?" value=${title} disabled=${busy} onInput=${(e) => setTitle(e.target.value)} onPaste=${attachments.onPaste} required />
    <textarea aria-label="Task details" placeholder="Details, context, or steps to reproduce… (optional) · Enter to create · Shift + Enter for a new line" rows="2" value=${description} disabled=${busy} onInput=${(e) => setDescription(e.target.value)} onPaste=${attachments.onPaste}
      onKeyDown=${(e) => {
		if (e.key === "Enter" && !e.shiftKey && !(e.metaKey || e.ctrlKey) && !e.isComposing) create(e);
	}} />
    <${AttachmentPicker} files=${files} controls=${attachments} disabled=${busy} />
    <div class="task-compose-actions"><label>Assign to <select aria-label="Task assignee" value=${assignee} disabled=${busy} onChange=${(e) => setAssignee(e.target.value)}>
      <option value="">Unassigned</option>
      ${!targetExists && m$1`<option value=${assignee} disabled>${assignee} (unavailable)</option>`}
      ${teams.length > 0 && m$1`<optgroup label="Teams">${teams.map((t) => m$1`<option value=${`t:${t.id}`}>${t.name}</option>`)}</optgroup>`}
      <optgroup label="Agents">${agents.map((r) => m$1`<option value=${r.user_id}>${r.user_id} · ${machineName(r.node)}${r.pane_alive ? "" : " (offline)"}</option>`)}</optgroup>
    </select></label><button class="act" disabled=${busy || attachments.uploading > 0 || !title.trim() || !targetExists}>${busy ? "Creating…" : "create task"}</button></div>
    ${!targetExists && m$1`<p class="task-compose-status">The selected assignee is unavailable. Choose another destination.</p>`}
    ${status && m$1`<p class="task-compose-status" role="status">${status}</p>`}
  </form>`;
	if (!folded) return form;
	return m$1`<details class="task-compose-fold" open=${!!(draft.title || draft.description || draft.files?.length)}>
    <summary>+ create a task${user ? ` for ${user}` : ""}</summary>
    ${form}
  </details>`;
}
function Kanban({ state, refresh }) {
	const agentIds = state.recipients.filter((r) => r.pane_alive).map((r) => r.user_id);
	const teams = state.teams || [];
	const byId = new Map(state.tasks.map((t) => [t.id, t]));
	return m$1`<div>
    <h2>tasks ${state.tasks.length > 0 && m$1`<span class="count">· ${state.tasks.length}</span>`}</h2>
    <${TaskComposer} key="board" state=${state} refresh=${refresh} />
    <div class="board">
      ${[
		["open", "open"],
		["picked_up", "picked up"],
		["done", "done"]
	].map(([status, label]) => {
		const all = state.tasks.filter((t) => t.status === status);
		const items = status === "done" ? [...all].sort((a, b) => b.updated_at - a.updated_at).slice(0, DONE_ON_BOARD) : all;
		return m$1`<div key=${status} class=${`col ${status}`}>
          <div class="colhead">${label}<span class="n">${all.length}</span></div>
          <div class="cards">
            ${items.length === 0 ? m$1`<div class="colempty">none</div>` : items.map((t) => m$1`<${TaskCard} key=${t.id} t=${t}
                  agentIds=${agentIds} teams=${teams}
                  blockers=${(t.depends_on || []).filter((d) => (byId.get(d) || {}).status !== "done")}
                  refresh=${refresh} />`)}
          </div>
          ${status === "done" && all.length > 0 && m$1`<a class="col-more" href=${historyHash({ status: "done" })}
            title="Search every task in the history view">${all.length > items.length ? `all ${all.length} done tasks →` : "search done tasks →"}</a>`}
        </div>`;
	})}
    </div>
  </div>`;
}
var AGENTS_VIEW_KEY = "agent-swarm:mobile-agents-view";
var SIDEBAR_VIEW_KEY = "agent-swarm:sidebar-agents-view";
var AGENTS_VIEWS = [["teams", "teams"], ["tiles", "tiles"]];
var COLLAPSED_TEAMS_KEY = "agent-swarm:collapsed-teams";
function readJSON(key, fallback) {
	try {
		return JSON.parse(localStorage.getItem(key) || "null") ?? fallback;
	} catch {
		return fallback;
	}
}
function TeamManage({ team, members, refresh, onDone }) {
	const [queen, setQueen] = d(team.queen || "");
	const [objective, setObjective] = d("");
	const [busy, setBusy] = d(false);
	const save = async (e) => {
		e.preventDefault();
		if (queen === (team.queen || "")) {
			onDone();
			return;
		}
		setBusy(true);
		const body = queen ? {
			queen,
			objective: objective.trim() || null
		} : { queen: null };
		const res = await fetch(`/teams/${team.id}`, {
			method: "PATCH",
			headers: JSONH,
			body: JSON.stringify(body)
		}).catch(() => null);
		setBusy(false);
		if (!res?.ok) {
			alert(`Could not change the queen of ${team.name}.`);
			return;
		}
		onDone();
		refresh();
	};
	const offlineQueen = team.queen && !members.some((r) => r.user_id === team.queen);
	return m$1`<form class="team-manage" onSubmit=${save}>
    <label>queen <select aria-label=${`Queen of ${team.name}`} value=${queen} disabled=${busy} onChange=${(e) => setQueen(e.target.value)}>
      <option value="">no queen</option>
      ${members.map((r) => m$1`<option key=${r.user_id} value=${r.user_id}>${r.user_id}</option>`)}
      ${offlineQueen && m$1`<option value=${team.queen}>${team.queen} (offline)</option>`}
    </select></label>
    ${queen && queen !== team.queen && m$1`<input type="text" aria-label="Objective for the queen" placeholder="objective (optional)"
      value=${objective} disabled=${busy} onInput=${(e) => setObjective(e.target.value)} />`}
    <div class="team-manage-actions">
      <button class="act" disabled=${busy}>${busy ? "saving…" : "save"}</button>
      <button type="button" class="mini" onClick=${onDone}>cancel</button>
    </div>
  </form>`;
}
async function removeTeam(team, refresh) {
	if (!confirm(`Remove team ${team.name}? Its agents keep running.`)) return;
	if (!(await fetch(`/teams/${team.id}`, { method: "DELETE" }).catch(() => null))?.ok) {
		alert(`Could not remove ${team.name}.`);
		return;
	}
	refresh();
}
function TeamBees({ state, refresh, machine, harness = null, unreadFor, focusUser = null }) {
	const [dragging, setDragging] = d(null);
	const [over, setOver] = d(null);
	const [managing, setManaging] = d(null);
	const [collapsed, setCollapsed] = d(() => new Set(readJSON(COLLAPSED_TEAMS_KEY, [])));
	const toggle = (key, open) => setCollapsed((prev) => {
		const next = new Set(prev);
		if (open) next.delete(key);
		else next.add(key);
		try {
			localStorage.setItem(COLLAPSED_TEAMS_KEY, JSON.stringify([...next]));
		} catch {}
		return next;
	});
	const live = state.recipients.filter((r) => r.pane_alive && agentShown(r, machine, harness));
	const offline = state.recipients.filter((r) => !r.pane_alive && !r.reserved && agentShown(r, machine, harness));
	const teams = state.teams || [];
	const groups = teams.map((t) => ({
		key: `t:${t.id}`,
		name: t.name,
		queen: t.queen,
		members: live.filter((r) => r.team_id === t.id).sort((a, b) => (b.user_id === t.queen) - (a.user_id === t.queen) || a.user_id.localeCompare(b.user_id)),
		gone: offline.filter((r) => r.team_id === t.id).map((r) => r.user_id).sort(),
		teamId: t.id
	}));
	const loners = live.filter((r) => !teams.some((t) => t.id === r.team_id)).sort((a, b) => a.user_id.localeCompare(b.user_id));
	const lonersGone = offline.filter((r) => !teams.some((t) => t.id === r.team_id)).map((r) => r.user_id).sort();
	groups.push({
		key: "none",
		name: "no team",
		queen: null,
		members: loners,
		gone: lonersGone,
		teamId: null
	});
	groups.sort((a, b) => !a.members.length - !b.members.length);
	if (!dragging) groups.splice(0, groups.length, ...groups.filter((g) => g.teamId !== null || g.members.length || g.gone.length));
	const stopOver = over === "stop";
	const stopDrop = agentDropProps((on) => setOver((cur) => on ? "stop" : cur === "stop" ? null : cur), (user) => {
		setDragging(null);
		const r = live.find((x) => x.user_id === user);
		if (r) stopAgent(r, state, focusUser, refresh);
	});
	return m$1`<div class="team-bees">
    ${!live.length && m$1`<p class="compact-hive-empty">No live ${harness ? `${harnessStyle(harness).label} ` : ""}agents${machine ? ` on ${machine}` : ""}.</p>`}
    ${groups.map((g) => {
		const busy = g.members.filter((r) => agentStatus(r) === "working").length;
		const attention = g.members.filter((r) => agentStatus(r) === "needs_attention").length;
		const drop = agentDropProps((on) => setOver((cur) => on ? g.key : cur === g.key ? null : cur), (user) => {
			setDragging(null);
			const from = live.find((r) => r.user_id === user);
			if (from && (teams.some((t) => t.id === from.team_id) ? from.team_id : null) !== g.teamId) moveAgentToTeam(user, g.teamId, refresh);
		});
		const team = g.teamId === null ? null : teams.find((t) => t.id === g.teamId);
		const empty = !g.members.length && !g.gone.length;
		return m$1`<details key=${g.key} class=${`team-bees-group ${g.key === "none" ? "loose" : ""} ${empty && !dragging ? "empty" : ""} ${over === g.key ? "over" : ""}`}
        open=${!collapsed.has(g.key) || managing === g.key} onToggle=${(e) => toggle(g.key, e.currentTarget.open)} ...${drop}>
      <summary><span class="team-bees-name">${g.name}</span>
        <span class="team-bees-counts">${g.members.length}${busy ? m$1` · <span class="working">${busy} working</span>` : ""}${attention ? m$1` · <span class="attn">${attention} need you</span>` : ""}</span>
        ${team && m$1`<button type="button" class="team-bees-manage" aria-pressed=${managing === g.key}
          aria-label=${`Pick queen for ${g.name}`} title=${team.queen ? `queen: ${team.queen} · change queen` : "pick a queen"}
          onClick=${(e) => {
			e.preventDefault();
			e.stopPropagation();
			setManaging((m) => m === g.key ? null : g.key);
		}}>♛</button>`}
        ${team && m$1`<button type="button" class="team-bees-manage team-bees-remove"
          aria-label=${`Remove team ${g.name}`} title="remove team (its agents keep running)"
          onClick=${(e) => {
			e.preventDefault();
			e.stopPropagation();
			removeTeam(team, refresh);
		}}>✕</button>`}</summary>
      ${managing === g.key && team && m$1`<${TeamManage} key=${`${g.key}:${team.queen}`} team=${team} members=${g.members} refresh=${refresh} onDone=${() => setManaging(null)} />`}
      <div class="team-bees-chips">${empty && dragging && m$1`<span class="team-bees-empty">drop here</span>`}${g.members.map((r) => {
			const st = STATE[agentStatus(r)] || STATE.unknown;
			return m$1`<a key=${r.user_id} class=${`team-mate ${focusUser === r.user_id ? "here" : ""}`}
          aria-current=${focusUser === r.user_id ? "page" : null} href=${`#/agent/${encodeURIComponent(r.user_id)}`}
          style=${`--machine:${machineColor(r.node)}`} title=${`${r.user_id} · ${machineName(r.node)} · ${st.word}`}
          draggable="true" onDragStart=${(e) => {
				e.dataTransfer.effectAllowed = "move";
				e.dataTransfer.setData(AGENT_DRAG_TYPE, r.user_id);
				e.dataTransfer.setData("text/plain", r.user_id);
				setDragging(r.user_id);
			}} onDragEnd=${() => {
				setDragging(null);
				setOver(null);
			}}>
          <${Bee} node=${r.node} flavor=${r.flavor} size="small" working=${st.cls === "working"} />
          <span class="team-mate-name">${r.user_id}</span>
          ${g.queen === r.user_id && m$1`<span class="crown" title="team queen">♛</span>`}
          ${state.supervisor && state.supervisor.user_id === r.user_id && m$1`<span class="crown supervisor" title="swarm supervisor">✪</span>`}
          <span class=${`status ${st.cls}`}></span>
          ${unreadFor(r.user_id) && m$1`<span class="team-mate-unread" title="new reply">●</span>`}
        </a>`;
		})}</div>
      ${g.gone.length > 0 && m$1`<div class="team-bees-offline"><span title=${g.gone.join(", ")}>${g.gone.length} offline: ${g.gone.join(", ")}</span>
        <${RetireButton} ids=${g.gone} refresh=${refresh} label=${g.gone.length > 1 ? `retire all ${g.gone.length}` : "retire"} /></div>`}
    </details>`;
	})}
    ${dragging && m$1`<div class=${`team-bees-stop ${stopOver ? "over" : ""}`} ...${stopDrop}>drop here to stop ${dragging}</div>`}
    <${NewTeam} refresh=${refresh} />
    <${SpawnControl} refresh=${refresh} nodes=${state.nodes || []} />
  </div>`;
}
function AgentsPanel({ state, refresh, machine, harness, setHarness, unreadFor, storageKey = AGENTS_VIEW_KEY, focusUser = null, onClose = null }) {
	const [view, setView] = d(() => {
		try {
			return localStorage.getItem(storageKey) === "tiles" ? "tiles" : "teams";
		} catch {
			return "teams";
		}
	});
	const pick = (v) => {
		setView(v);
		try {
			localStorage.setItem(storageKey, v);
		} catch {}
	};
	const live = state.recipients.filter((r) => r.pane_alive && agentShown(r, machine, harness)).length;
	const filter = m$1`<${HarnessFilter} recipients=${state.recipients} harness=${harness} setHarness=${setHarness} />`;
	return m$1`<div class="agents-panel">
    ${onClose && m$1`<div class="roster-heading"><h2>agents ${live > 0 && m$1`<span class="count">· ${live}</span>`}</h2>
      ${filter}
      <button type="button" class="mini" aria-label="Hide agents" onClick=${onClose}>Hide →</button></div>`}
    <div class="agents-view-switch" role="group" aria-label="Agents view">
      <span>view</span>
      ${AGENTS_VIEWS.map(([v, label]) => m$1`<button key=${v} type="button" aria-pressed=${view === v} onClick=${() => pick(v)}>${label}</button>`)}
      ${!onClose && filter}
    </div>
    ${view === "tiles" ? m$1`<${CompactBees} state=${state} machine=${machine} harness=${harness} />` : m$1`<${TeamBees} state=${state} refresh=${refresh} machine=${machine} harness=${harness} unreadFor=${unreadFor} focusUser=${focusUser} />`}
  </div>`;
}
function Overview({ state, refresh, machine, harness, setHarness, unreadFor }) {
	return m$1`<div>
    <h2>activity</h2>
    <${HiveView} state=${state} refresh=${refresh} machine=${machine} harness=${harness} setHarness=${setHarness}
      compactBody=${m$1`<${AgentsPanel} state=${state} refresh=${refresh} machine=${machine} harness=${harness} setHarness=${setHarness} unreadFor=${unreadFor} />`} />
    <${Kanban} state=${state} refresh=${refresh} />
  </div>`;
}
function Scope({ user, refresh }) {
	const [open, setOpen] = d(false);
	const [data, setData] = d(null);
	const preRef = A(null);
	const pinned = A(true);
	h(() => {
		let live = true;
		setData(null);
		if (!open) return;
		pinned.current = true;
		const load = async () => {
			try {
				const d = await (await fetch(`/api/peek/${encodeURIComponent(user)}`)).json();
				if (live) setData(d);
			} catch {}
		};
		load();
		const t = setInterval(load, PEEK_MS);
		return () => {
			live = false;
			clearInterval(t);
		};
	}, [user, open]);
	h(() => {
		const pre = preRef.current;
		if (pre && pinned.current) pre.scrollTop = pre.scrollHeight;
	}, [data]);
	const onScroll = (e) => {
		const el = e.target;
		pinned.current = el.scrollTop + el.clientHeight >= el.scrollHeight - 8;
	};
	return m$1`<details class="scope" onToggle=${(e) => setOpen(e.currentTarget.open)}>
    <summary class="bar">
      <span class="t">terminal</span>
      <span>${data ? data.pane_label : ""}</span>
      <span style="margin-left:auto">${open ? "live capture · 2s" : "show terminal"}</span>
    </summary>
    ${data && data.error ? m$1`<div class="err">could not capture pane: ${data.error}</div>` : m$1`<pre ref=${preRef} onScroll=${onScroll}>${data ? (data.text || "").replace(/\s+$/, "") || "(pane is blank)" : "capturing pane…"}</pre>`}
    <${TerminalInput} user=${user} />
  </details>`;
}
var TERMINAL_KEYS = [
	["Escape", "esc"],
	["Up", "↑"],
	["Down", "↓"],
	["Enter", "⏎"],
	["Tab", "tab"]
];
function typeInto(user, body) {
	return fetch(`/agents/${encodeURIComponent(user)}/terminal`, {
		method: "POST",
		headers: JSONH,
		body: JSON.stringify(body)
	});
}
async function failure(res) {
	return (await res.json().catch(() => ({}))).detail?.error || `error ${res.status}`;
}
function TerminalInput({ user }) {
	const [text, setText] = d("");
	const [busy, setBusy] = d(false);
	const [status, setStatus] = d("");
	const send = async (body) => {
		setBusy(true);
		setStatus("");
		const res = await typeInto(user, body);
		setBusy(false);
		if (!res.ok) {
			setStatus(await failure(res));
			return false;
		}
		return true;
	};
	const submit = async (e) => {
		e.preventDefault();
		if (!text.trim() || busy) return;
		if (await send({ text })) setText("");
	};
	return m$1`<form class="composer terminal-input" onSubmit=${submit}>
    <div class="compose-row">
      <span class="mark">$</span>
      <input type="text" value=${text} disabled=${busy} aria-label=${`Type into ${user}'s terminal`}
        placeholder="type into the terminal, e.g. /fast or /model sonnet"
        onInput=${(e) => setText(e.target.value)} />
      <button type="submit" class="mini" disabled=${busy || !text.trim()}>enter</button>
    </div>
    <div class="compose-meta">
      <span>keys</span>
      ${TERMINAL_KEYS.map(([key, label]) => m$1`<button key=${key} type="button" class="mini"
        disabled=${busy} title=${`Press ${key} in ${user}'s pane`} onClick=${() => send({ key })}>${label}</button>`)}
      ${status && m$1`<span class="err">${status}</span>`}
    </div>
  </form>`;
}
var pendingSends = new EventTarget();
var pendingSeq = 0;
function newClientId() {
	return Array.from(crypto.getRandomValues(/* @__PURE__ */ new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
}
var RESEND_DELAYS_MS = [
	1e3,
	3e3,
	6e3
];
function MessageComposer({ recipient, refresh, autoFocus = false, focused = false }) {
	const narrow = useMedia(COMPACT_LAYOUT);
	const compact = focused && narrow;
	const [optionsOpen, setOptionsOpen] = d(false);
	const [text, setText] = d("");
	const [context, setContext] = d("");
	const [images, setImages] = d([]);
	const [status, setStatus] = d("");
	const [sending, setSending] = d(false);
	const [retryOf, setRetryOf] = d(null);
	const composerRef = A(null);
	const draftKey = `agent-swarm:draft:${recipient}:thread`;
	const attachments = useAttachments(images, setImages, setStatus, draftKey);
	const { uploading, dragging } = attachments;
	h(() => {
		try {
			const draft = JSON.parse(localStorage.getItem(draftKey) || "null");
			setText(draft?.text || "");
			setContext(draft?.context || "");
			setImages(Array.isArray(draft?.images) ? draft.images : []);
			setRetryOf(draft?.retryOf || null);
			setStatus("");
		} catch {}
	}, [draftKey]);
	h(() => {
		const el = composerRef.current;
		const busy = document.activeElement?.closest?.("input, textarea, select, [contenteditable]");
		if (autoFocus && el && (!busy || busy === el) && !matchMedia("(pointer: coarse)").matches) el.focus({ preventScroll: true });
	}, [autoFocus, recipient]);
	h(() => {
		const el = composerRef.current;
		if (!el) return;
		el.style.height = "auto";
		el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
	}, [text, compact]);
	h(() => {
		let timer;
		const onOutcome = (e) => {
			if (e.detail.draftKey !== draftKey) return;
			const { status: next, draft } = e.detail;
			if (draft) {
				setText((t) => t || draft.text);
				setContext((c) => c || draft.context);
				setImages((imgs) => imgs.length ? imgs : draft.images);
				setRetryOf(draft.retryOf || null);
			}
			setStatus(next);
			clearTimeout(timer);
			if (next === "delivered") timer = setTimeout(() => setStatus((s) => s === "delivered" ? "" : s), 2500);
		};
		pendingSends.addEventListener("outcome", onOutcome);
		return () => {
			clearTimeout(timer);
			pendingSends.removeEventListener("outcome", onOutcome);
		};
	}, [draftKey]);
	const loadedKey = A(null);
	_(() => {
		if (loadedKey.current !== draftKey) {
			loadedKey.current = draftKey;
			return;
		}
		try {
			if (text || context || images.length) localStorage.setItem(draftKey, JSON.stringify({
				text,
				context,
				images,
				retryOf
			}));
			else localStorage.removeItem(draftKey);
		} catch {}
	}, [
		draftKey,
		text,
		context,
		images,
		retryOf
	]);
	const canSend = !sending && uploading === 0 && (text.trim() || images.length > 0);
	const send = async (e) => {
		e.preventDefault();
		const content = text.trim();
		if (!canSend) return;
		const clientId = draftClientId({
			text,
			context,
			images
		}, retryOf, newClientId);
		const draft = {
			text,
			context,
			images,
			retryOf: {
				clientId,
				text,
				context,
				images
			}
		};
		const pending = {
			id: `pending-${++pendingSeq}`,
			pending: true,
			delivered: true,
			status: "delivered",
			sender: "owner",
			recipient,
			content,
			context: context.trim() || null,
			attachments: images,
			ts: Date.now() / 1e3
		};
		setSending(true);
		setOptionsOpen(false);
		setStatus("sending…");
		setText("");
		setContext("");
		setImages([]);
		setRetryOf(null);
		try {
			localStorage.removeItem(draftKey);
		} catch {}
		pendingSends.dispatchEvent(new CustomEvent("add", { detail: pending }));
		const report = (detail) => pendingSends.dispatchEvent(new CustomEvent("outcome", { detail: {
			draftKey,
			...detail
		} }));
		const keepDraft = () => {
			try {
				localStorage.setItem(draftKey, JSON.stringify(draft));
			} catch {}
		};
		const attempt = async () => {
			try {
				const r = await fetch("/owner/send", {
					method: "POST",
					headers: JSONH,
					body: JSON.stringify({
						recipient,
						content,
						context: pending.context,
						attachments: images,
						client_id: clientId
					})
				});
				let body = null;
				try {
					body = await r.json();
				} catch {
					body = null;
				}
				return deliveryOutcome(r.ok, body);
			} catch (err) {
				return unansweredOutcome(err);
			}
		};
		let outcome = await attempt();
		for (const delay of RESEND_DELAYS_MS) {
			if (outcome.status !== "uncertain") break;
			report({ status: `not confirmed (${outcome.reason}); checking again…` });
			await new Promise((resolve) => setTimeout(resolve, delay));
			outcome = await attempt();
		}
		if (outcome.status === "delivered") report({ status: "delivered" });
		else if (outcome.status === "unknown") report({ status: `outcome unknown: ${outcome.reason}. The agent may have it; see the marked message.` });
		else if (outcome.status === "uncertain") {
			keepDraft();
			report({
				status: `not confirmed: ${outcome.reason}. Draft kept; sending it unchanged is safe, it will not arrive twice`,
				draft
			});
		} else {
			keepDraft();
			report({
				status: `delivery failed: ${outcome.reason}. Draft kept`,
				draft
			});
		}
		await refresh();
		pendingSends.dispatchEvent(new CustomEvent("settle", { detail: pending.id }));
		setSending(false);
	};
	const clearDraft = () => {
		setText("");
		setContext("");
		setImages([]);
		setStatus("");
		composerRef.current?.focus();
	};
	const submit = m$1`<button class="act" type="submit" disabled=${!canSend}>
    ${sending ? "sending…" : uploading ? "uploading…" : "send"}
  </button>`;
	const optionsId = `compose-options-${encodeURIComponent(recipient)}`;
	return m$1`<form class=${`composer ${compact ? "compact-composer" : ""} ${optionsOpen ? "options-open" : ""} ${dragging ? "dragging" : ""}`} onSubmit=${send} ...${sending ? {} : attachments.dropProps}>
    <div class="compose-row">
      ${compact ? m$1`<button type="button" class="compose-options-toggle" aria-label="Message options"
        aria-expanded=${optionsOpen} aria-controls=${optionsId}
        onClick=${() => setOptionsOpen((v) => !v)}>${optionsOpen ? "×" : "+"}</button>` : m$1`<span class="mark">❯</span>`}
      <textarea ref=${composerRef} value=${text} rows=${compact ? 1 : 2}
        onInput=${(e) => setText(e.target.value)}
        onPaste=${sending ? void 0 : attachments.onPaste}
        onKeyDown=${(e) => {
		if (e.key === "Enter" && !e.shiftKey && !(e.metaKey || e.ctrlKey)) send(e);
	}}
        placeholder=${compact ? "Message…" : `Message ${recipient}… (paste or drop files)`} aria-label=${`Message ${recipient} as owner`} />
      ${compact && submit}
    </div>
    <${AttachmentPicker} files=${images} controls=${attachments} disabled=${sending} />
    <div id=${optionsId} class="compose-meta" hidden=${compact && !optionsOpen}>
      <input class="context" type="text" value=${context} onInput=${(e) => setContext(e.target.value)}
        placeholder="context tag (optional)" aria-label="Optional context tag" />
      <span class="count">${text.length} character${text.length === 1 ? "" : "s"}${images.length > 0 ? ` · ${images.length} file${images.length === 1 ? "" : "s"}` : ""}</span>
      ${!compact && m$1`<span class="hint">Enter to send · Shift + Enter for a new line</span>`}
      <div class="actions">
        ${!compact && status && m$1`<span class=${status.startsWith("delivery failed") || status.startsWith("image not added") ? "error" : "sent"} role="status">${status}</span>`}
        ${(text || context || images.length > 0) && m$1`<button type="button" class="mini" onClick=${clearDraft}>clear</button>`}
        ${!compact && submit}
      </div>
    </div>
    ${compact && status && m$1`<div class="compose-status" role="status">${status}</div>`}
  </form>`;
}
var FOCUS_FONT = {
	min: 12,
	max: 26,
	start: 16,
	step: 2
};
var FOCUS_FONT_KEY = "agent-swarm:focus-font";
function sentByViewer(sender, a, b, page) {
	if (a === "owner" || b === "owner") return sender === "owner";
	if (page === a || page === b) return sender === page;
	return sender !== a;
}
function Thread({ a, b, msgs, freshIds, now, refresh, page = null, agents = null }) {
	const boxRef = A(null);
	const follower = A(null);
	if (!follower.current) follower.current = createBottomFollower();
	const resizeRef = A(null);
	const previousHistory = A(null);
	const [historyHeight, setHistoryHeight] = d(null);
	const recipient = a === "owner" ? b : b === "owner" ? a : null;
	const other = recipient || a === b ? null : page === a ? b : page === b ? a : null;
	const peer = other && agents?.has(other) ? other : null;
	const [expanded, setExpanded] = d(!!recipient);
	const [focused, setFocused] = d(() => !!(recipient && switchCarry?.focus));
	const threadRef = A(null);
	const focusMac = /Mac|iPhone|iPad/.test(navigator.platform);
	const focusShortcut = focusMac ? "⌘⇧L" : "Ctrl+Shift+L";
	const [focusFont, setFocusFont] = d(() => {
		try {
			return Number(localStorage.getItem(FOCUS_FONT_KEY)) || FOCUS_FONT.start;
		} catch {
			return FOCUS_FONT.start;
		}
	});
	const stepFont = (by) => setFocusFont((size) => {
		const next = Math.max(FOCUS_FONT.min, Math.min(FOCUS_FONT.max, size + by));
		try {
			localStorage.setItem(FOCUS_FONT_KEY, String(next));
		} catch {}
		return next;
	});
	const savedScroll = A(0);
	const bodyId = `thread-${encodeURIComponent(pairKey(a, b))}`;
	_(() => {
		if (expanded && boxRef.current) boxRef.current.scrollTop = savedScroll.current;
	}, [expanded]);
	const lastId = msgs.length ? msgs[msgs.length - 1].id : null;
	_(() => {
		const el = boxRef.current;
		if (!el || !expanded) return;
		const previous = previousHistory.current;
		if (previous && previous.first !== msgs[0]?.id && msgs.some((m) => m.id === previous.first)) el.scrollTop = previous.top + el.scrollHeight - previous.height;
		const stick = () => {
			follower.current.follow(el);
			previousHistory.current = {
				first: msgs[0]?.id,
				height: el.scrollHeight,
				top: el.scrollTop
			};
		};
		const ro = new ResizeObserver(stick);
		ro.observe(el);
		for (const child of el.children) ro.observe(child);
		stick();
		return () => ro.disconnect();
	}, [
		msgs.length,
		lastId,
		historyHeight,
		expanded
	]);
	const toggleFocus = () => {
		setExpanded(true);
		setFocused((v) => !v);
	};
	h(() => {
		document.documentElement.classList.toggle("thread-focus-open", focused);
		return () => document.documentElement.classList.remove("thread-focus-open");
	}, [focused]);
	_(() => {
		const viewport = window.visualViewport;
		if (!focused || !viewport) return;
		const el = threadRef.current;
		const fitViewport = () => {
			el.style.setProperty("--chat-top", `${viewport.offsetTop}px`);
			el.style.setProperty("--chat-height", `${viewport.height}px`);
		};
		fitViewport();
		viewport.addEventListener("resize", fitViewport);
		viewport.addEventListener("scroll", fitViewport);
		return () => {
			viewport.removeEventListener("resize", fitViewport);
			viewport.removeEventListener("scroll", fitViewport);
		};
	}, [focused]);
	_(() => {
		const onKey = (e) => {
			if (e.isComposing || document.querySelector(".quick-switch[open]")) return;
			if (e.key === "Escape" && focused) {
				e.preventDefault();
				e.stopImmediatePropagation();
				setFocused(false);
				return;
			}
			const modifier = focusMac ? e.metaKey && !e.ctrlKey : e.ctrlKey && !e.metaKey;
			if (page && (recipient || focused) && (!document.querySelector(".thread.focused") || focused) && e.code === "KeyL" && e.shiftKey && modifier && !e.altKey) {
				e.preventDefault();
				e.stopImmediatePropagation();
				if (!e.repeat) toggleFocus();
			}
		};
		addEventListener("keydown", onKey, true);
		return () => removeEventListener("keydown", onKey, true);
	}, [focused, recipient]);
	const onScroll = (e) => {
		if (!expanded) return;
		savedScroll.current = e.currentTarget.scrollTop;
		if (previousHistory.current) previousHistory.current.top = e.currentTarget.scrollTop;
		follower.current.onScroll(e.currentTarget);
	};
	const resizeBounds = () => ({
		min: 120,
		max: Math.max(120, Math.floor(innerHeight * .85))
	});
	const resizeTo = (height) => {
		const { min, max } = resizeBounds();
		setHistoryHeight(Math.max(min, Math.min(max, Math.round(height))));
	};
	const resizeStart = (e) => {
		e.preventDefault();
		e.currentTarget.setPointerCapture(e.pointerId);
		resizeRef.current = {
			y: e.clientY,
			height: boxRef.current.getBoundingClientRect().height
		};
	};
	const resizeMove = (e) => {
		if (!resizeRef.current) return;
		resizeTo(resizeRef.current.height + e.clientY - resizeRef.current.y);
	};
	const resizeEnd = (e) => {
		if (!resizeRef.current) return;
		resizeRef.current = null;
		if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
	};
	const resizeKey = (e) => {
		const current = historyHeight ?? boxRef.current.getBoundingClientRect().height;
		const { min, max } = resizeBounds();
		const next = e.key === "ArrowUp" ? current - 40 : e.key === "ArrowDown" ? current + 40 : e.key === "Home" ? min : e.key === "End" ? max : null;
		if (next === null) return;
		e.preventDefault();
		resizeTo(next);
	};
	return m$1`<div ref=${threadRef} class=${`thread ${focused ? "focused" : ""}`} role=${focused ? "dialog" : null}
      style=${focused ? { "--focus-font": `${focusFont}px` } : null}
      aria-label=${focused ? `Conversation ${a} and ${b}` : null}>
    <div class="thread-head">
      <button type="button" class="bar thread-toggle" aria-expanded=${expanded} aria-controls=${bodyId}
          disabled=${focused} onClick=${() => setExpanded((v) => !v)}>
        <span class="thread-chevron" aria-hidden="true">${expanded ? "▾" : "▸"}</span>
        <span class="thread-participants">${disp(a)} <span class="swap">⇄</span> ${disp(b)}</span>
        <span class="n">${msgs.length} msg${msgs.length === 1 ? "" : "s"}</span>
      </button>
      ${focused && m$1`
        <button type="button" class="thread-focus" title="Smaller text" aria-label="Smaller text"
          disabled=${focusFont <= FOCUS_FONT.min} onClick=${() => stepFont(-FOCUS_FONT.step)}>A−</button>
        <button type="button" class="thread-focus" title="Larger text" aria-label="Larger text"
          disabled=${focusFont >= FOCUS_FONT.max} onClick=${() => stepFont(FOCUS_FONT.step)}>A+</button>`}
      ${peer && !focused && m$1`<a class="thread-focus thread-goto" href=${`#/agent/${encodeURIComponent(peer)}`}
        title=${`Go to ${peer}'s page to message them`}>open ${peer} →</a>`}
      <button type="button" class="thread-focus thread-focus-toggle" aria-pressed=${focused} onClick=${toggleFocus}
        aria-label=${focused ? "Close focused conversation" : "Focus conversation"}
        title=${focused ? `Back to the page (Esc or ${focusShortcut})` : `Expand this conversation to fill the window${recipient ? ` (${focusShortcut})` : ""}`}>
        <span aria-hidden="true">${focused ? "✕" : "⤢"}</span><span class="focus-label">${focused ? " close" : " focus"}</span>${recipient && m$1` <span class="focus-key-hint">${focusShortcut}</span>`}</button>
    </div>
    <div id=${bodyId} class="thread-body" hidden=${!expanded}>
    <div class="msgs" ref=${boxRef} onScroll=${onScroll}
      style=${historyHeight === null ? null : { height: `${historyHeight}px` }}>
      ${msgs.map((m) => m$1`
        <div key=${m.id} class=${[
		"msg",
		sentByViewer(m.sender, a, b, page) ? "right" : "",
		freshIds.has(m.id) ? "fresh" : "",
		m.status === "failed" ? "failed" : m.status === "unknown" ? "unknown" : "",
		m.sender === "owner" ? "from-owner" : "",
		m.pending ? "pending" : ""
	].join(" ")}>
          <div class="bubble">${m.content && m$1`<div class="md"
            dangerouslySetInnerHTML=${{ __html: renderMarkdown(shellNewlines(m.content)) }} />`}${m.attachments?.length > 0 && m$1`<div class=${`msg-images ${m.content ? "" : "only"}`}>
            ${m.attachments.map((name) => m$1`<${AttachmentLink} key=${name} name=${name} />`)}
          </div>`}</div>
          <div class="tag">${disp(m.sender)}${m.context && m$1` · <span class="ctx">${m.context}</span>`} · ${m.pending ? "sending…" : rel(m.ts, now)}${m.status === "failed" && m$1` · <span class="ctx">undelivered${m.delivery_error ? `: ${m.delivery_error}` : ""}</span>`}${m.status === "unknown" && m$1` · <span class="ctx">outcome unknown${m.delivery_error ? `: ${m.delivery_error}` : ""}</span>${m.sender === "owner" && m$1` <${Resend} m=${m} refresh=${refresh} />`}`}</div>
        </div>`)}
    </div>
    <button type="button" class="history-resizer" role="separator" aria-orientation="horizontal"
      aria-label="Resize conversation history"
      aria-valuemin="120" aria-valuemax=${resizeBounds().max}
      aria-valuenow=${historyHeight ?? 340} title="Drag to resize conversation history"
      onPointerDown=${resizeStart} onPointerMove=${resizeMove}
      onPointerUp=${resizeEnd} onPointerCancel=${resizeEnd} onKeyDown=${resizeKey}>
      <span>drag to resize history</span>
    </button>
    ${recipient && m$1`<${MessageComposer} recipient=${recipient} refresh=${refresh} autoFocus=${!!page} focused=${focused} />`}
    </div>
  </div>`;
}
function Doing({ summaries, now }) {
	if (summaries.length === 0) return m$1`<div class="doing-box empty-doing">No status yet. Agents post one with
      <code>agent-swarm status "working on …"</code>; Claude Code and Codex pane titles
      show up here too.</div>`;
	const [cur, ...past] = summaries.slice(0, 6);
	const line = (s) => m$1`<span class="src" title=${SUMMARY_SOURCE[s.source] || s.source}>${s.source === "agent" ? "✎" : "▭"}</span>`;
	return m$1`<div class="doing-box">
    <div class="now">${line(cur)} ${cur.text} <span class="age">· ${rel(cur.ts, now)}</span></div>
    ${past.length > 0 && m$1`<details class="status-history"><summary>${past.length} earlier ${past.length === 1 ? "update" : "updates"}</summary><ol class="past">
      ${past.map((s) => m$1`<li>${line(s)} ${s.text} <span class="age">· ${rel(s.ts, now)}</span></li>`)}
    </ol></details>`}
  </div>`;
}
function AgentTaskRow({ t, taskIds, agentIds, refresh }) {
	const [error, setError] = d("");
	const assign = async (e) => {
		const result = await patchTask(t.id, { assignee: e.target.value || null });
		if (!result.ok) {
			setError(result.error);
			return;
		}
		setError("");
		refresh();
	};
	return m$1`<div class=${`trow ${t.status}`}>
    <span class="tid">#${t.id}</span>
    <span class="t">${t.title}<${AttachmentList} files=${t.attachments} />
      ${t.note && m$1`<details class="task-row-note"><summary>How to verify</summary><div>${t.note}</div></details>`}
    </span>
    <span class=${`pill ${t.status}`}>${t.status.replace("_", " ")}</span>
    <select title="assignee" aria-label=${`Assign task #${t.id}`} value=${t.assignee || ""}
      disabled=${t.status === "done"} onChange=${assign}>
      <option value="">unassigned</option>
      ${taskIds.map((a) => m$1`<option key=${a} value=${a}>${a}${agentIds.includes(a) ? "" : " (stopped)"}</option>`)}
    </select>
    <${TaskStatusActions} task=${t} refresh=${refresh} />
    ${error && m$1`<span class="task-action-error" role="alert">${error}</span>`}
  </div>`;
}
var switchCarry = null;
function useTeammateKeys(members) {
	const current = A(null);
	current.current = members;
	h(() => {
		const onKey = (e) => {
			if (!e.altKey || e.ctrlKey || e.metaKey || document.querySelector(".quick-switch[open]")) return;
			const members = current.current;
			const here = location.hash.startsWith("#/agent/") ? decodeURIComponent(location.hash.slice(8)) : null;
			const by = e.code === "BracketRight" ? 1 : e.code === "BracketLeft" ? -1 : 0;
			const known = members && members.some((m) => m.user_id === here);
			const next = by && known && stepTeammate(members, here, by);
			if (!next) return;
			e.preventDefault();
			switchCarry = {
				composer: !!document.activeElement?.closest?.(".thread .composer"),
				focus: !!document.querySelector(".thread.focused")
			};
			location.hash = `#/agent/${encodeURIComponent(next)}`;
		};
		addEventListener("keydown", onKey);
		return () => removeEventListener("keydown", onKey);
	}, []);
}
function TeamStrip({ crew, user, unreadFor }) {
	return m$1`<nav class="team-strip" aria-label=${`Team ${crew.team.name}`}>
    <span class="team-strip-name">${crew.team.name}</span>
    ${crew.members.map((m) => {
		const st = STATE[agentStatus(m)] || STATE.unknown;
		const here = m.user_id === user;
		return m$1`<a key=${m.user_id} href=${`#/agent/${encodeURIComponent(m.user_id)}`}
        class=${`team-mate ${here ? "here" : ""}`} aria-current=${here ? "page" : null}
        title=${`${m.user_id} · ${st.word}`}>
        <${Bee} node=${m.node} flavor=${m.flavor} size="small" working=${st.cls === "working"} />
        <span class="team-mate-name">${m.user_id}</span>
        ${crew.team.queen === m.user_id && m$1`<span class="crown" title="team queen">♛</span>`}
        <span class=${`status ${st.cls}`}></span>
        ${unreadFor(m.user_id) && m$1`<span class="team-mate-unread" title="new reply">●</span>`}
      </a>`;
	})}
    ${crew.members.length > 1 && m$1`<span class="team-strip-hint">Alt+[ / Alt+]</span>`}
  </nav>`;
}
var CHATS_ROUTE = "#/chats";
var chatsQuery = () => new URLSearchParams(location.hash.split("?")[1] || "").get("q") || "";
function snippet(text, words, width = 240) {
	const flat = (text || "").replace(/\s+/g, " ").trim();
	const at = words.length ? flat.toLowerCase().indexOf(words[0]) : -1;
	const start = at > 80 ? at - 60 : 0;
	const cut = flat.slice(start, start + width);
	return `${start ? "…" : ""}${cut}${start + width < flat.length ? "…" : ""}`;
}
function marked(text, words) {
	if (!words.length) return text;
	const re = new RegExp(`(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
	return text.split(re).map((part, i) => i % 2 ? m$1`<mark>${part}</mark>` : part);
}
function ChatsView({ state, unreadFor }) {
	const [full, setFull] = d(null);
	const [query, setQuery] = d(chatsQuery);
	h(() => {
		let live = true;
		fetch("/messages?user=owner&limit=100000").then((r) => r.json()).then((d) => {
			if (live) setFull(d.messages || []);
		}).catch(() => {
			if (live) setFull([]);
		});
		return () => {
			live = false;
		};
	}, []);
	const update = (q) => {
		setQuery(q);
		history.replaceState(null, "", q ? `${CHATS_ROUTE}?q=${encodeURIComponent(q)}` : CHATS_ROUTE);
	};
	const words = query.toLowerCase().split(/\s+/).filter(Boolean);
	const chats = T(() => ownerChats([...state.messages, ...full || []], query), [
		state.messages,
		full,
		query
	]);
	const byId = new Map(state.recipients.map((r) => [r.user_id, r]));
	return m$1`<div class="chats">
    <h2>chats <span class="count">· ${chats.length}${full === null ? " · loading full history…" : ""}</span></h2>
    <input type="text" class="h-search chats-search" value=${query} autofocus
      placeholder="search your conversations: who did I ask about…"
      aria-label="Search your conversations" onInput=${(e) => update(e.target.value)}
      onKeyDown=${(e) => {
		if (e.key === "Escape" && query) {
			e.stopPropagation();
			update("");
		}
	}} />
    ${chats.length === 0 ? m$1`<div class="empty">${query ? m$1`No conversation mentions "<b>${query}</b>".` : "No conversations yet."}</div>` : m$1`<div class="chat-list">${chats.map((c) => {
		const r = byId.get(c.agent);
		const st = STATE[r ? agentStatus(r) : "unknown"] || STATE.unknown;
		const m = c.match || c.last;
		return m$1`<a key=${c.agent} class="chat-row" href=${`#/agent/${encodeURIComponent(c.agent)}`}>
            ${r ? m$1`<${Bee} node=${r.node} flavor=${r.flavor} size="small" working=${st.cls === "working"} />` : m$1`<span class="chat-gone" aria-hidden="true">◌</span>`}
            <span class="chat-main">
              <span class="chat-who">${c.agent}<span class=${`status ${st.cls}`} title=${r ? st.word : "no longer registered"}></span>
                ${unreadFor(c.agent) && m$1`<span class="team-mate-unread" title="new reply">●</span>`}
                <span class="chat-when">${rel(m.ts, state.now)}${c.match ? ` · ${c.matches} match${c.matches === 1 ? "" : "es"}` : ` · ${c.count} msg${c.count === 1 ? "" : "s"}`}</span></span>
              <span class="chat-line"><b>${m.sender === "owner" ? "you" : m.sender}:</b> ${marked(snippet(m.content, words), words)}</span>
            </span>
          </a>`;
	})}</div>`}
  </div>`;
}
function FocusView({ user, state, refresh, freshIds, unreadFor }) {
	const history = useAgentHistory(user);
	const messages = [...new Map([...history.messages, ...state.messages].filter((m) => m.sender === user || m.recipient === user).map((m) => [m.id, m])).values()].sort((a, b) => a.ts - b.ts || a.id - b.id);
	const crew = T(() => teammates(state.recipients, state.teams, user), [
		state.recipients,
		state.teams,
		user
	]);
	useTeammateKeys(T(() => crew && crew.members, [crew && crew.members.map((m) => m.user_id).join(" ")]));
	h(() => {
		const carry = switchCarry;
		switchCarry = null;
		if (carry?.composer) requestAnimationFrame(() => document.querySelector(".thread .composer textarea")?.focus());
	}, [user]);
	const threadOrder = A(/* @__PURE__ */ new Map());
	const nextThreadOrder = A(0);
	const registered = new Set(state.recipients.map((x) => x.user_id));
	const r = state.recipients.find((x) => x.user_id === user);
	if (!r) return m$1`<div class="empty">No agent named "${user}".
    <br /><br /><button class="mini" onClick=${() => {
		location.hash = "#/";
	}}>back to overview</button></div>`;
	const flavor = (r.flavor || "generic").toLowerCase();
	const status = agentStatus(r);
	const st = STATE[status] || STATE.unknown;
	const detail = r.activity && r.activity.detail;
	const myTasks = state.tasks.filter((t) => t.assignee === user);
	const agentIds = state.recipients.filter((x) => x.pane_alive).map((x) => x.user_id);
	const taskIds = agentIds.includes(user) ? agentIds : agentIds.concat(user);
	const groups = /* @__PURE__ */ new Map();
	for (const m of messages) {
		if (m.sender !== user && m.recipient !== user) continue;
		const k = pairKey(m.sender, m.recipient);
		if (!groups.has(k)) groups.set(k, []);
		groups.get(k).push(m);
	}
	for (const key of groups.keys()) if (!threadOrder.current.has(key)) threadOrder.current.set(key, nextThreadOrder.current++);
	const ownerThread = pairKey("owner", user);
	const threads = [...groups.entries()].sort(([a], [b]) => {
		if (a === ownerThread) return -1;
		if (b === ownerThread) return 1;
		return threadOrder.current.get(a) - threadOrder.current.get(b);
	}).map(([, msgs]) => msgs);
	const hasOwnerThread = groups.has(ownerThread);
	return m$1`<div>
    <div class="focus-top">
      <button type="button" class="focus-back" onClick=${() => {
		location.hash = "#/";
	}}>← back to overview</button>
      ${crew && m$1`<${TeamStrip} crew=${crew} user=${user} unreadFor=${unreadFor} />`}
    </div>
    <div class="fhead">
      <${Bee} node=${r.node} flavor=${r.flavor} working=${status === "working"} />
      <div class="who">
        <div class="nm">${user}<span class=${`status ${st.cls}`} title=${st.word}></span></div>
        <div class="meta">
          <span class="chip">${FLAVOR_ICON[flavor] || FLAVOR_ICON.generic} ${flavor}</span>
          <${ModelLabel} r=${r} refresh=${refresh} /> · <${MachineBadge} node=${r.node} /> · pane <b>${r.pane_label}</b>${r.pane_alive ? "" : " (stopped)"}
          <${JumpToPane} r=${r} />
          <${CompactButton} r=${r} />
          <${StopAgentButton} key=${user} r=${r} refresh=${refresh} />
          · joined ${rel(r.registered_at, state.now)}
          · <span style=${`color:${st.color}`}>${st.word}</span>${status === "needs_attention" && detail ? m$1` <span class="attn">${detail}</span>` : ""}
        </div>
        ${r.instructions && m$1`<div class="inst">"${r.instructions}"</div>`}
      </div>
    </div>
    <h2>status updates</h2>
    <${Doing} summaries=${r.summaries || []} now=${state.now} />
    <${Scope} key=${user} user=${user} refresh=${refresh} />
    <h2>conversations ${threads.length > 0 && m$1`<span class="count">· ${threads.length}</span>`}</h2>
    ${history.error && m$1`<p role="status">${history.error}</p>`}
    ${!history.loaded && !history.error && m$1`<p role="status">Loading conversation history…</p>`}
    ${history.more && m$1`<button type="button" class="mini" disabled=${history.busy} onClick=${history.loadOlder}>
      ${history.busy ? "Loading older messages…" : "Load older messages"}</button>`}
    ${threads.length === 0 ? m$1`<div class="thread">${history.loaded && m$1`<div class="empty">Nothing yet. Start a conversation with ${user} below.</div>`}
          <${MessageComposer} recipient=${user} refresh=${refresh} autoFocus /></div>` : threads.map((msgs) => {
		const [a, b] = pairKey(msgs[0].sender, msgs[0].recipient).split(" ");
		return m$1`<${Thread} key=${pairKey(a, b)} a=${a} b=${b} msgs=${msgs} page=${user} agents=${registered}
            freshIds=${freshIds} now=${state.now} refresh=${refresh} />`;
	})}
    ${threads.length > 0 && !hasOwnerThread && m$1`<div class="thread" style="margin-top:14px">
      <div class="bar">${disp("owner")} <span class="swap">⇄</span> ${user}</div>
      <${MessageComposer} recipient=${user} refresh=${refresh} autoFocus />
    </div>`}
    <h2 style="margin-top:26px">tasks ${myTasks.length > 0 && m$1`<span class="count">· ${myTasks.length}</span>`}
      ${myTasks.length > 0 && m$1`<a class="h2-link" href=${historyHash({ agent: user })}>search ${user}'s history →</a>`}</h2>
    <${TaskComposer} key=${user} user=${user} state=${state} refresh=${refresh} folded />
    ${myTasks.length === 0 ? m$1`<div class="empty">No tasks assigned to ${user} yet.</div>` : myTasks.map((t) => m$1`<${AgentTaskRow} key=${t.id} t=${t} taskIds=${taskIds}
          agentIds=${agentIds} refresh=${refresh} />`)}
  </div>`;
}
var STANDALONE = matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
var reportAttention = attentionReporter(globalThis.__TAURI__?.core?.invoke);
function App() {
	const compact = useMedia(COMPACT_LAYOUT);
	const [state, setState] = d(null);
	const [machine, setMachine] = d(null);
	const [harness, setHarness] = d(null);
	const tabsRef = A([]);
	tabsRef.current = state?.tabs || [];
	const [rosterOpen, setRosterOpen] = d(() => {
		try {
			const saved = localStorage.getItem("swarm-roster-open");
			return saved === null ? true : saved === "true";
		} catch {
			return true;
		}
	});
	const rosterOpenRef = A(rosterOpen);
	rosterOpenRef.current = rosterOpen;
	const toggleRef = A(null);
	const updateRoster = (open) => {
		rosterOpenRef.current = open;
		setRosterOpen(open);
		try {
			localStorage.setItem("swarm-roster-open", String(open));
		} catch {}
	};
	const toggleRoster = () => updateRoster(!rosterOpen);
	const closeRoster = () => {
		updateRoster(false);
		requestAnimationFrame(() => toggleRef.current?.focus());
	};
	const mac = /Mac|iPhone|iPad/.test(navigator.platform);
	const rosterShortcut = mac ? "⌘B" : "Ctrl+B";
	_(() => {
		const onKey = (e) => {
			const modifier = mac ? e.metaKey && !e.ctrlKey : e.ctrlKey && !e.metaKey;
			if (compact || !modifier || e.code !== "KeyB" || e.shiftKey || e.altKey || e.isComposing || e.defaultPrevented || document.activeElement?.isContentEditable || document.querySelector("dialog[open], .thread.focused")) return;
			e.preventDefault();
			if (e.repeat) return;
			if (rosterOpenRef.current && document.activeElement?.closest?.("#agent-sidebar")) closeRoster();
			else updateRoster(!rosterOpenRef.current);
		};
		addEventListener("keydown", onKey);
		return () => removeEventListener("keydown", onKey);
	}, [compact, mac]);
	const [connected, setConnected] = d(true);
	const [clock, setClock] = d((/* @__PURE__ */ new Date()).toLocaleTimeString());
	const [route, setRoute] = d(location.hash);
	const [freshIds, setFreshIds] = d(/* @__PURE__ */ new Set());
	const seen = A({
		maxId: 0,
		first: true,
		byAgent: {}
	});
	const [pending, setPending] = d([]);
	h(() => {
		const add = (e) => setPending((p) => [...p, e.detail]);
		const settle = (e) => setPending((p) => p.filter((m) => m.id !== e.detail));
		pendingSends.addEventListener("add", add);
		pendingSends.addEventListener("settle", settle);
		return () => {
			pendingSends.removeEventListener("add", add);
			pendingSends.removeEventListener("settle", settle);
		};
	}, []);
	const focusUser = route.startsWith("#/agent/") ? decodeURIComponent(route.slice(8)) : null;
	const onHistory = route.startsWith(HISTORY_ROUTE);
	const onChats = route.startsWith(CHATS_ROUTE);
	const onTab = route.startsWith("#/tab/") ? decodeURIComponent(route.slice(TAB_ROUTE.length)) : null;
	const onOverview = !focusUser && !onHistory && !onChats && !onTab;
	const previousView = A({
		focusUser,
		onHistory
	});
	h(() => {
		const before = previousView.current;
		previousView.current = {
			focusUser,
			onHistory
		};
		if ((before.focusUser !== focusUser || before.onHistory !== onHistory) && compact) document.querySelector(".stage")?.scrollIntoView({ block: "start" });
	}, [
		focusUser,
		onHistory,
		compact
	]);
	const poll = async () => {
		try {
			const s = await (await fetch("/api/state")).json();
			const st = seen.current;
			const maxId = Math.max(st.maxId, ...s.messages.map((m) => m.id), 0);
			const fresh = s.messages.filter((m) => m.id > st.maxId);
			if (!st.first && fresh.length) setFreshIds(new Set(fresh.map((m) => m.id)));
			for (const rec of s.recipients) if (st.first || !(rec.user_id in st.byAgent)) st.byAgent[rec.user_id] = maxId;
			st.maxId = maxId;
			if (st.first && location.hash.startsWith("#/agent/") && !s.recipients.some((r) => r.user_id === decodeURIComponent(location.hash.slice(8)))) location.replace("#/");
			st.first = false;
			setState(s);
			setConnected(true);
			reportAttention(s.recipients);
		} catch {
			setConnected(false);
		}
	};
	h(() => {
		poll();
		const t = setInterval(poll, POLL_MS);
		const c = setInterval(() => setClock((/* @__PURE__ */ new Date()).toLocaleTimeString()), 1e3);
		const onHash = () => setRoute(location.hash);
		const onKey = (e) => {
			if (e.key === "Escape" && !e.defaultPrevented && !e.repeat && ![
				"INPUT",
				"SELECT",
				"TEXTAREA"
			].includes(document.activeElement.tagName) && !document.activeElement.isContentEditable) {
				if (rosterOpenRef.current) closeRoster();
			}
			if (e.code === "KeyH" && e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey && !e.isComposing && !document.querySelector(".quick-switch[open]") && location.hash !== "#/" && location.hash !== "") {
				e.preventDefault();
				location.hash = "#/";
			}
			const modifier = mac ? e.metaKey && !e.ctrlKey : e.ctrlKey && !e.metaKey;
			const by = e.code === "BracketRight" ? 1 : e.code === "BracketLeft" ? -1 : 0;
			if (by && modifier && e.shiftKey && !e.altKey && !e.isComposing && !document.querySelector(".quick-switch[open]")) {
				e.preventDefault();
				location.hash = stepView(location.hash, [
					"#/",
					CHATS_ROUTE,
					...tabsRef.current.map(tabHash),
					HISTORY_ROUTE
				], by);
			}
		};
		addEventListener("hashchange", onHash);
		addEventListener("keydown", onKey);
		return () => {
			clearInterval(t);
			clearInterval(c);
			removeEventListener("hashchange", onHash);
			removeEventListener("keydown", onKey);
		};
	}, []);
	if (focusUser && seen.current.byAgent[focusUser] !== void 0) seen.current.byAgent[focusUser] = seen.current.maxId;
	const unreadFor = (u) => {
		if (!state || u === focusUser) return false;
		const since = seen.current.byAgent[u] ?? seen.current.maxId;
		return state.messages.some((m) => m.id > since && m.sender === u && m.recipient === "owner");
	};
	const header = m$1`<header class="top">
    <h1 style="cursor:pointer" onClick=${() => {
		location.hash = "#/";
	}}>Buzz</h1>
    <nav class="views" aria-label="views" title=${`Switch views: ${mac ? "⌘⇧[ / ⌘⇧]" : "Ctrl+Shift+[ / ]"}`}>
      <a href="#/" class=${onOverview ? "on" : ""} title=${`Overview (${mac ? "⌥H" : "Alt+H"})`} aria-keyshortcuts="Alt+h">overview</a>
      <a href=${CHATS_ROUTE} class=${onChats ? "on" : ""}>chats</a>
      ${(state?.tabs || []).map((t) => m$1`<a key=${t} href=${tabHash(t)} class=${onTab === t ? "on" : ""}>${t}</a>`)}
      <a href=${HISTORY_ROUTE} class=${onHistory ? "on" : ""}>task history</a>
    </nav>
    <${QuickSwitcher} state=${state} navigate=${(user, previous) => {
		if (location.hash === focusHash(user)) return;
		switchCarry = {
			composer: !!previous?.closest?.(".thread .composer"),
			focus: !!document.querySelector(".thread.focused")
		};
		setMachine(null);
		location.hash = focusHash(user);
	}} />
    <div class="right">
      <span><span class=${`beacon ${connected ? "" : "down"}`}></span>${connected ? "watching" : "server unreachable"}</span>
      <span>${clock}</span>
      ${STANDALONE && m$1`<button type="button" class="reload" title="Reload the dashboard"
        onClick=${() => location.reload()}>↻ reload</button>`}
    </div>
  </header>`;
	if (!state) return m$1`${header}<main><div class="stage"><div class="empty">connecting…</div></div></main>`;
	const view = pending.length ? {
		...state,
		messages: [...state.messages, ...pending]
	} : state;
	return m$1`<main class=${`dashboard-layout ${rosterOpen ? "roster-open" : ""}`}>
    <div class="main-col">
    ${header}
    ${onOverview && m$1`<${MachineBar} state=${state} machine=${machine} selectMachine=${setMachine} />`}
    ${!compact && m$1`<button type="button" ref=${toggleRef} class=${`roster-toggle ${rosterOpen ? "is-open" : ""}`}
      aria-expanded=${rosterOpen} aria-controls="agent-sidebar" onClick=${toggleRoster}
      title=${`Toggle agent sidebar (${rosterShortcut})`} aria-keyshortcuts=${mac ? "Meta+b" : "Control+b"}>
      ${rosterOpen ? "Agents ›" : "‹ Agents"} · ${state.recipients.filter((r) => r.pane_alive).length} · ${rosterShortcut}
    </button>`}
    <div class="stage">
      ${focusUser ? m$1`<${FocusView} key=${focusUser} user=${focusUser} state=${view} refresh=${poll} freshIds=${freshIds} unreadFor=${unreadFor} />` : onHistory ? m$1`<${HistoryView} state=${state} />` : onChats ? m$1`<${ChatsView} state=${state} unreadFor=${unreadFor} />` : onTab !== null ? m$1`<${TabView} name=${onTab} tabs=${state.tabs || []} />` : m$1`<${Overview} state=${state} refresh=${poll} machine=${machine} harness=${harness} setHarness=${setHarness} unreadFor=${unreadFor} />`}
    </div>
    </div>
    ${!compact && m$1`<div id="agent-sidebar" class=${`roster-drawer ${rosterOpen ? "is-open" : ""}`} inert=${!rosterOpen} aria-hidden=${!rosterOpen}>
      <aside class="roster">
        <${AgentsPanel} state=${state} refresh=${poll} machine=${onOverview ? machine : null} harness=${harness} setHarness=${setHarness} unreadFor=${unreadFor}
          storageKey=${SIDEBAR_VIEW_KEY} focusUser=${focusUser} onClose=${closeRoster} />
      </aside>
    </div>`}
  </main>`;
}
R(m$1`<${App} />`, document.getElementById("app"));
//#endregion
