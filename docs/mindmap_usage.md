# Maia Mind-Map Guide

## Overview
Maia mind-maps now support two map modes:

- `structure`: document hierarchy (sections, subsections, pages, source links)
- `evidence`: claims + supporting evidence graph used during Q&A

The UI and backend both carry `map_type` so users can switch views without losing context.

## Frontend Controls
In Chat sidebar (`Mind-map` card):

- `Generate automatically`
- `Include reasoning map`
- `Max depth`
- `Map type` (`Structure` or `Evidence`)

In the Info Panel mind-map viewer:

- switch between `Structure` and `Evidence` map variants
- `Expand` / `Collapse` branches
- `Balanced` / `Horizontal` layout
- `Focus` mode for branch-centric zoom
- export: `PNG`, `JSON`, `Markdown`
- `Save` and `Share`

## API Endpoints

### Build map by source
`GET /api/mindmap?sourceId=<source_id>&mapType=structure&maxDepth=4&includeReasoningMap=true`

Query params:

- `sourceId` (required): indexed source id
- `mapType`: `structure` or `evidence`
- `maxDepth`: 2-8
- `includeReasoningMap`: `true`/`false`

### Export map JSON
`GET /api/mindmap/export/json?sourceId=<source_id>&mapType=structure&maxDepth=4&includeReasoningMap=true`

### Export map Markdown
`GET /api/mindmap/export/markdown?sourceId=<source_id>&mapType=structure&maxDepth=4&includeReasoningMap=true`

## Backend Builders

Core builder entrypoint:

- `maia.mindmap.indexer.build_knowledge_map(...)`

Specialized builders:

- `maia.mindmap.structure_map.build_structure_map(...)`
- `maia.mindmap.evidence_map.build_evidence_map(...)`
- `maia.mindmap.indexer.parse_pdf_structure(...)`
- `maia.mindmap.indexer.crawl_web(...)`

Optional output fields:

- `reasoning_map` when enabled
- `tree` normalized hierarchical view
- `variants` alternate map payload (`structure` <-> `evidence`)
