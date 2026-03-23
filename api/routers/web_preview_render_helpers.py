from __future__ import annotations

import html
import json
import re
from typing import Any, Callable
from urllib.parse import quote_plus, urljoin


def sanitize_and_inject_preview_html(
    *,
    html_text: str,
    source_url: str,
    highlight_phrases: list[str],
    highlight_scope: str,
    preview_viewport: str,
    normalize_target_url_fn: Callable[[Any], str],
    should_uncloak_tag_fn: Callable[[str], bool],
    strip_cloak_attrs_from_tag_fn: Callable[[str], str],
    normalize_highlight_scope_fn: Callable[[Any], str],
    normalize_preview_viewport_fn: Callable[[Any], str],
    default_highlight_scope: str,
    default_preview_viewport: str,
) -> str:
    text = str(html_text or "")
    lower = text.lower()
    if "<html" not in lower:
        text = f"<!doctype html><html><head></head><body>{text}</body></html>"
    if "<head" not in text.lower():
        text = re.sub(
            r"(<html\b[^>]*>)",
            r"\1<head></head>",
            text,
            count=1,
            flags=re.IGNORECASE,
        )
    if "<body" not in text.lower():
        if re.search(r"</head>", text, flags=re.IGNORECASE):
            text = re.sub(r"</head>", "</head><body>", text, count=1, flags=re.IGNORECASE)
            if re.search(r"</html>", text, flags=re.IGNORECASE):
                text = re.sub(r"</html>", "</body></html>", text, count=1, flags=re.IGNORECASE)
            else:
                text = f"{text}</body>"

    text = re.sub(
        r"<script\b[^>]*>.*?</script>",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(
        r"<meta\b[^>]*http-equiv\s*=\s*['\"]?refresh['\"]?[^>]*>",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"<meta\b[^>]*\bname\s*=\s*(?:['\"]viewport['\"]|viewport)(?:\s[^>]*)?>",
        "",
        text,
        flags=re.IGNORECASE,
    )

    def _rewrite_cloak_tag(match: re.Match[str]) -> str:
        raw_tag = str(match.group(0) or "")
        if not re.search(r"\b(?:x-cloak|v-cloak|data-cloak)\b", raw_tag, flags=re.IGNORECASE):
            return raw_tag
        if not should_uncloak_tag_fn(raw_tag):
            return raw_tag
        return strip_cloak_attrs_from_tag_fn(raw_tag)

    text = re.sub(r"<[^>]+>", _rewrite_cloak_tag, text)

    def _rewrite_anchor_href(match: re.Match[str]) -> str:
        prefix = str(match.group(1) or "")
        raw_href = " ".join(str(match.group(2) or "").split()).strip()
        suffix = str(match.group(3) or "")
        if raw_href.startswith("#"):
            return f"{prefix}{html.escape(raw_href, quote=True)}{suffix}"
        absolute = normalize_target_url_fn(urljoin(source_url, html.unescape(raw_href)))
        preview_href = f"/api/web/preview?url={quote_plus(absolute)}" if absolute else "#"
        safe_href = html.escape(preview_href, quote=True)
        patched_suffix = re.sub(
            r"\starget\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)",
            "",
            suffix,
            flags=re.IGNORECASE,
        )
        patched_suffix = re.sub(
            r"\srel\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)",
            "",
            patched_suffix,
            flags=re.IGNORECASE,
        )
        patched_suffix = patched_suffix[:-1] + " target='_self' rel='noopener noreferrer'>"
        return f"{prefix}{safe_href}{patched_suffix}"

    text = re.sub(
        r"(<a\b[^>]*\bhref=['\"])([^'\"]+)(['\"][^>]*>)",
        _rewrite_anchor_href,
        text,
        flags=re.IGNORECASE,
    )

    scope = normalize_highlight_scope_fn(highlight_scope or default_highlight_scope)
    viewport_mode = normalize_preview_viewport_fn(preview_viewport or default_preview_viewport)
    viewport_meta = (
        "<meta name='viewport' content='width=1280,initial-scale=1'/>"
        if viewport_mode == "desktop"
        else "<meta name='viewport' content='width=device-width,initial-scale=1'/>"
    )

    style_block = (
        "<style>"
        "html,body{max-width:100% !important;overflow-x:hidden !important;}"
        "*,*::before,*::after{box-sizing:border-box;}"
        "img,video,canvas,svg,iframe,embed,object{max-width:100% !important;height:auto !important;}"
        "table{max-width:100% !important;width:100% !important;table-layout:fixed;}"
        "pre,code,kbd,samp{white-space:pre-wrap !important;overflow-wrap:anywhere !important;word-break:break-word !important;}"
        "[style*='width:'],[width]{max-width:100% !important;}"
        ".maia-citation-region{"
        "background:rgba(255,233,107,.2) !important;"
        "border-radius:.5em;"
        "box-shadow:inset 0 0 0 1px rgba(173,121,0,.22);"
        "padding:.16em .26em;"
        "}"
        "mark.maia-citation-highlight{"
        "background:#ffe96b !important;"
        "color:inherit !important;"
        "padding:.14em .24em;"
        "margin:0 .01em;"
        "border-radius:.24em;"
        "line-height:1.45;"
        "-webkit-box-decoration-break:clone;"
        "box-decoration-break:clone;"
        "box-shadow:0 0 0 1px rgba(173,121,0,.25);"
        "}"
        "body[data-maia-highlight-scope='tight'] mark.maia-citation-highlight{padding:.06em .14em;border-radius:.16em;line-height:1.25;}"
        "body[data-maia-highlight-scope='sentence'] mark.maia-citation-highlight{padding:.16em .30em;border-radius:.26em;line-height:1.55;}"
        "body[data-maia-highlight-scope='context'] mark.maia-citation-highlight,body[data-maia-highlight-scope='block'] mark.maia-citation-highlight{padding:.20em .40em;border-radius:.32em;line-height:1.65;}"
        ".maia-reader-banner{display:none !important;}"
        ".opacity-0{opacity:1 !important;}"
        "img.js-image,img[class*='js-image'],picture img{opacity:1 !important;visibility:visible !important;}"
        ".maia-citation-region mark.maia-citation-highlight{background:#ffe14f !important;}"
        "mark.maia-citation-highlight.maia-citation-active{"
        "outline:2px solid rgba(173,121,0,.45);"
        "outline-offset:1px;"
        "animation:maia-citation-land 1.8s ease-out 0.5s 1 forwards;"
        "}"
        "@keyframes maia-citation-land{"
        "0%{background:#ffd000 !important;box-shadow:0 0 0 4px rgba(255,200,0,.45),0 0 0 1px rgba(173,121,0,.25);}"
        "60%{background:#ffe96b !important;box-shadow:0 0 0 2px rgba(255,200,0,.2),0 0 0 1px rgba(173,121,0,.25);}"
        "100%{background:#ffe96b !important;box-shadow:0 0 0 1px rgba(173,121,0,.25);}"
        "}"
        "</style>"
    )

    script_block = (
        "<script>"
        "(function(){"
        "function run(attempt){"
        "const phrases="
        + json.dumps(highlight_phrases, ensure_ascii=True)
        + ";"
        "const highlightScope="
        + json.dumps(scope, ensure_ascii=True)
        + ";"
        "const cleaned=[...new Set((phrases||[]).map((row)=>String(row||'').trim()).filter((row)=>row.length>=8))].slice(0,3);"
        "if(!cleaned.length){return;}"
        "if(!document.body){if((attempt||0)<4){setTimeout(()=>run((attempt||0)+1),600);}return;}"
        "document.body.setAttribute('data-maia-highlight-scope',highlightScope);"
        "const skipTags=new Set(['SCRIPT','STYLE','NOSCRIPT','MARK','TEXTAREA','TITLE']);"
        "function nearestBoundary(raw,idx,direction){"
        "const marks=['.','!','?',String.fromCharCode(10)];"
        "if(direction<0){let found=-1;for(const mark of marks){const pos=raw.lastIndexOf(mark,idx);if(pos>found){found=pos;}}return found;}"
        "let found=raw.length;"
        "for(const mark of marks){const pos=raw.indexOf(mark,idx);if(pos>=0&&pos<found){found=pos;}}"
        "return found===raw.length?-1:found;"
        "}"
        "function expandedRange(raw,idx,queryLength){"
        "let start=idx;let end=idx+queryLength;"
        "if(highlightScope==='context'){start=Math.max(0,idx-90);end=Math.min(raw.length,idx+queryLength+90);}"
        "if(highlightScope==='sentence'||highlightScope==='block'){"
        "const left=nearestBoundary(raw,idx-1,-1);"
        "const right=nearestBoundary(raw,idx+queryLength,1);"
        "start=left>=0?left+1:0;"
        "end=right>=0?right+1:raw.length;"
        "}"
        "while(start<raw.length&&/\\s/.test(raw[start])){start+=1;}"
        "while(end>start&&/\\s/.test(raw[end-1])){end-=1;}"
        "if(end<=start){start=idx;end=idx+queryLength;}"
        "return [start,end];"
        "}"
        "function findAndMark(phrase,maxHits){"
        "const query=String(phrase||'');"
        "if(!query){return 0;}"
        "const qLower=query.toLowerCase();"
        "const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT,{acceptNode(node){"
        "if(!node||!node.parentElement){return NodeFilter.FILTER_REJECT;}"
        "if(skipTags.has(node.parentElement.tagName)){return NodeFilter.FILTER_REJECT;}"
        "const value=String(node.nodeValue||'');"
        "if(!value||value.trim().length<qLower.length){return NodeFilter.FILTER_REJECT;}"
        "if(String(node.parentElement.className||'').includes('maia-citation-highlight')){return NodeFilter.FILTER_REJECT;}"
        "return value.toLowerCase().includes(qLower)?NodeFilter.FILTER_ACCEPT:NodeFilter.FILTER_REJECT;"
        "}});"
        "const nodes=[];let current=null;"
        "while((current=walker.nextNode())){nodes.push(current);}"
        "let hits=0;"
        "for(const node of nodes){"
        "if(hits>=maxHits){break;}"
        "const raw=String(node.nodeValue||'');"
        "const idx=raw.toLowerCase().indexOf(qLower);"
        "if(idx<0){continue;}"
        "const range=expandedRange(raw,idx,query.length);"
        "const start=range[0];"
        "const end=range[1];"
        "const before=raw.slice(0,start);"
        "const match=raw.slice(start,end);"
        "const after=raw.slice(end);"
        "const frag=document.createDocumentFragment();"
        "if(before){frag.appendChild(document.createTextNode(before));}"
        "const mark=document.createElement('mark');"
        "mark.className='maia-citation-highlight';"
        "mark.textContent=match;"
        "frag.appendChild(mark);"
        "if(after){frag.appendChild(document.createTextNode(after));}"
        "if(node.parentNode){node.parentNode.replaceChild(frag,node);hits+=1;}"
        "}"
        "return hits;"
        "}"
        "let total=0;"
        "for(const phrase of cleaned){"
        "total+=findAndMark(phrase,total>0?1:3);"
        "if(total>=3){break;}"
        "}"
        "const first=document.querySelector('mark.maia-citation-highlight');"
        "if(first){first.classList.add('maia-citation-active');"
        "const region=(first.closest('p,li,blockquote,td,th,h1,h2,h3,h4,h5,h6,figcaption')||first.parentElement);"
        "if((highlightScope==='context'||highlightScope==='block')&&region&&region!==document.body&&region.classList){region.classList.add('maia-citation-region');}"
        "const doScroll=()=>{try{first.scrollIntoView({block:'center',inline:'nearest',behavior:'smooth'});}catch(_err){}};"
        "setTimeout(doScroll,500);"
        "setTimeout(doScroll,1500);}"
        "}"
        "if(document.readyState==='loading'){"
        "document.addEventListener('DOMContentLoaded',function(){"
        "run(0);setTimeout(function(){run(1);},800);setTimeout(function(){run(2);},2000);"
        "});"
        "}else{"
        "run(0);setTimeout(function(){run(1);},800);setTimeout(function(){run(2);},2000);"
        "}"
        "})();"
        "</script>"
    )

    base_early = f"<base href='{html.escape(source_url, quote=True)}'/>{viewport_meta}"
    head_open_re = re.compile(r"(<head\b[^>]*>)", re.IGNORECASE)
    if head_open_re.search(text):
        text = head_open_re.sub(lambda m: f"{m.group(1)}{base_early}", text, count=1)
    else:
        text = f"<head>{base_early}</head>{text}"

    if re.search(r"</head>", text, flags=re.IGNORECASE):
        text = re.sub(
            r"</head>",
            lambda _match: f"{style_block}</head>",
            text,
            count=1,
            flags=re.IGNORECASE,
        )
    else:
        text = f"{text}{style_block}"
    if re.search(r"</body>", text, flags=re.IGNORECASE):
        text = re.sub(
            r"</body>",
            lambda _match: f"{script_block}</body>",
            text,
            count=1,
            flags=re.IGNORECASE,
        )
    else:
        text = f"{text}{script_block}"
    return text
