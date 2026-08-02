// SVGO config for sc-controller-cc's SVGs.
//
// These SVGs are not just artwork: the GUI reads element ids (AREA_*, "button",
// recolor targets, control ids), <rect> geometry for input-test/hover areas, the
// viewBox for coordinate math, display:none overlay layers, and custom attributes
// such as scc-button-scale. So we keep those intact and only strip the cruft
// (editor metadata, comments, redundant precision, etc.).
module.exports = {
	multipass: true,
	js2svg: { indent: 0, pretty: false },
	plugins: [
		{
			name: 'preset-default',
			params: {
				overrides: {
					cleanupIds: false,           // keep AREA_*, "button", recolor/control ids
					removeViewBox: false,        // coordinate math depends on the viewBox
					removeHiddenElems: false,    // display:none input-test areas must survive
					convertShapeToPath: false,   // areas are read as <rect x/y/width/height>
					removeUnknownsAndDefaults: false, // keep scc-button-scale + other custom attrs
					removeUselessStrokeAndFill: false, // recolor relies on explicit fill/stroke
					removeEmptyContainers: false, // keep empty anchor groups like <g id="controller">
					// button-image glyphs wrap art as <g id="button"><g transform=norm><path/></g></g>;
					// the GUI OVERWRITES the "button" group's transform when placing the glyph, so the
					// normalisation transform must stay on an inner element. Don't collapse/hoist groups,
					// or `id="button"` lands on the path and its transform gets clobbered (glyph flies off).
					collapseGroups: false,
					moveElemsAttrsToGroup: false,
					moveGroupAttrsToElems: false,
					// The GUI's SVGEditor.parse_transform regex only accepts comma-separated
					// numbers ([-0-9.,]), so a space-separated translate(a b) silently fails to
					// match and the element is treated as untransformed (e.g. the sc/deck
					// "controller" group's offset is lost, shifting every placed button). Keep
					// transforms in their authored comma form.
					convertTransform: false,
				},
			},
		},
	],
};
