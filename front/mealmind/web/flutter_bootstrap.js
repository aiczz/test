{{flutter_js}}
{{flutter_build_config}}

// Version both scripts: a query on index.html alone does not refresh main.dart.js.
const buildVersion = 'delete-custom-choices-20261010-v9';
for (const build of _flutter.buildConfig.builds) {
  if (build.mainJsPath) build.mainJsPath += '?v=' + buildVersion;
}
_flutter.loader.load({config: {canvasKitBaseUrl: 'canvaskit/'}});
