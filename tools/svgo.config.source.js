// SVGO config for the generator-parsed *source* assets (tools/sc2-source.svg,
// tools/sc2-assets/scnovo-grips-fim.svg).
//
// gen_sc2_image.py finds elements by inkscape:label and by id (g1/g6/g7), reads
// path `d` with a small custom parser (_svgpath.py, M/L/C/Z only), and queries
// bounding boxes via `inkscape --query-all`. So unlike the shipped SVGs, here we
// must also keep the inkscape namespace, the group structure and the path data
// as-authored. Savings are therefore modest (comments/metadata/precision only),
// but the generator keeps working and the files stay Inkscape-editable.
module.exports = {
	multipass: true,
	js2svg: { indent: 0, pretty: false },
	plugins: [
		{
			name: 'preset-default',
			params: {
				overrides: {
					cleanupIds: false,
					removeViewBox: false,
					removeHiddenElems: false,
					convertShapeToPath: false,
					removeUnknownsAndDefaults: false,
					removeUselessStrokeAndFill: false,
					removeEmptyContainers: false,
					removeEditorsNSData: false,   // keep inkscape:label (generator maps elements by it)
					collapseGroups: false,        // keep g1 and its label'd children / g6,g7 intact
					convertPathData: false,       // _svgpath parses `d`; don't rewrite path commands
					convertTransform: false,      // keep transforms comma-separated (GUI parse_transform can't read spaces)
					collapseGroups: false,        // <g id="button"> structure is overwritten by the GUI; don't flatten
					moveGroupAttrsToElems: false, // keep transforms where the generator reads them
					moveElemsAttrsToGroup: false,
				},
			},
		},
	],
};
