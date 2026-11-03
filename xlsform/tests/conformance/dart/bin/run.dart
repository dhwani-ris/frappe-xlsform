// Evaluate emitted XLSForm expressions with the mForm SDK's own interpreter
// (frappe-mobile-sdk lib/src/utils/js_expression.dart), the way DependsOnEvaluator does:
// scope {doc, parent}, JS truthiness, and any JsEvalException reported as an error,
// because the SDK would silently fall back to a default there.
//
// usage: dart run bin/run.dart <cases.json>   (SDK file is linked in as lib/js_expression.dart)
import 'dart:convert';
import 'dart:io';

import '../lib/js_expression.dart';

void main(List<String> args) {
  final cases = jsonDecode(File(args[0]).readAsStringSync()) as List;
  final out = <Map<String, Object?>>[];
  for (final c in cases.cast<Map<String, dynamic>>()) {
    final doc = Map<String, Object?>.from(c['doc'] as Map);
    doc.putIfAbsent('docstatus', () => 0);
    final parent = c['parent'] == null ? doc : Map<String, Object?>.from(c['parent'] as Map);
    try {
      final scope = {'doc': doc, 'parent': parent};
      if (c['value'] == true) {
        final v = evalJsExpression(c['js'] as String, scope);
        out.add({'id': c['id'], 'result': _str(v)});
      } else {
        out.add({'id': c['id'], 'result': evalJsExpressionAsBool(c['js'] as String, scope)});
      }
    } catch (e) {
      out.add({'id': c['id'], 'error': e.toString()});
    }
  }
  stdout.write(jsonEncode(out));
}

String _str(Object? v) {
  if (v == null) return '';
  if (v is double && v == v.truncateToDouble() && v.isFinite) return v.toInt().toString();
  return v.toString();
}
