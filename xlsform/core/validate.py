"""Run the five validation stages in order (REQUIREMENTS.md section 7).

Stages 1–2 stop the pipeline when they fail, because later stages can't run on a workbook
that can't be read or a tree that can't be built. Stages 3–5 always run, except that the
compiler-backed stages 4 and 5 need a form without stage 3 errors; when they are skipped
the result says so, so the designer knows more checks will follow.
"""

from dataclasses import dataclass, field

from xlsform.core import compiler, diff, meaning, reader, structure
from xlsform.core.form import Form
from xlsform.core.i18n import N_, tr
from xlsform.core.issues import ERROR, Issue, sort_key


@dataclass
class ValidateOptions:
	max_upload_mb: float = 5
	max_questions: int = 400
	max_choices_per_list: int = 20000
	max_expression_length: int = 2000
	row_budget_bytes: int = 60000
	prefix: str = "XF"
	published_version: str | None = None
	previous_meta: dict | None = None
	files: dict[str, bytes] = field(default_factory=dict)
	allow_web: bool = True
	taken_doctypes: set[str] = field(default_factory=set)
	reserved_fieldnames: set[str] = field(default_factory=set)


@dataclass
class Result:
	issues: list[Issue] = field(default_factory=list)
	skipped: list[dict] = field(default_factory=list)
	form: Form | None = None
	analysis: meaning.Analysis | None = None
	plan: dict | None = None
	change_summary: dict | None = None

	@property
	def ok(self) -> bool:
		return not any(i.severity == ERROR for i in self.issues)

	def report(self) -> dict:
		return {
			"issues": [i.as_dict() for i in self.issues],
			"skipped": self.skipped,
		}


def validate(content: bytes, filename: str, opts: ValidateOptions | None = None) -> Result:
	opts = opts or ValidateOptions()
	result = Result()

	wb, issues = reader.read_workbook(content, filename, opts.max_upload_mb)
	result.issues += issues
	if wb is None:
		return _finish(result, from_stage=2)

	form, issues = structure.build_form(wb, filename)
	result.issues += issues
	if form is None or any(i.severity == ERROR for i in issues):
		return _finish(result, from_stage=3)
	result.form = form

	analysis, issues = meaning.check(
		form,
		meaning.Options(
			max_choices_per_list=opts.max_choices_per_list,
			max_expression_length=opts.max_expression_length,
			published_version=opts.published_version,
			files=opts.files,
			allow_web=opts.allow_web,
		),
	)
	result.issues += issues
	result.analysis = analysis
	if any(i.severity == ERROR for i in issues):
		return _finish(result, from_stage=4)

	plan = compiler.compile_form(
		form,
		analysis,
		opts.previous_meta,
		compiler.CompileSettings(
			prefix=opts.prefix,
			row_budget_bytes=opts.row_budget_bytes,
			max_questions=opts.max_questions,
			taken_doctypes=opts.taken_doctypes,
			reserved_fieldnames=opts.reserved_fieldnames,
		),
	)
	result.issues += plan.pop("issues")
	result.plan = plan

	summary, issues = diff.diff(form, analysis, opts.previous_meta)
	result.issues += issues
	result.change_summary = summary
	return _finish(result)


STAGE_NAMES = {
	2: N_("structure"),
	3: N_("question types, choice lists and formulas"),
	4: N_("Frappe limits"),
	5: N_("changes from the published version"),
}


def _finish(result: Result, from_stage: int | None = None) -> Result:
	result.issues.sort(key=sort_key)
	if from_stage:
		for stage in range(from_stage, 6):
			result.skipped.append(
				{
					"stage": stage,
					"message": tr(
						N_("Checks for {what} will run after the errors above are fixed."),
						what=tr(STAGE_NAMES[stage]),
					),
				}
			)
	return result
