import argparse
import ast
import string
from collections import Counter
from pathlib import Path

import polib

TASK_STRING_ATTRS = {"name", "description"}
CONFIG_TYPE_META = {
    "type",
    "options",
    "buttons",
    "drop_down",
    "multi_selection",
    "global",
    "text_edit",
    "button",
}


def positional_field_specs(template):
    """返回模板中位置字段的规格列表（按出现顺序，含空字段 `{}`）。

    使用 Python 的 format string 解析器而非正则，以便正确区分转义花括号
    `{{`/`}}`，并把空字段 `{}` 计为第 0 号位置字段。自动编号字段（`{}`）与
    显式编号字段（`{0}`）都归入位置字段计数；具名字段（`{name}`）不计入。
    模板语法非法时返回 None，表示无法判定，交由调用方跳过该项校验。
    """
    try:
        parsed = list(string.Formatter().parse(template))
    except ValueError:
        return None
    specs = []
    for _, field_name, _, _ in parsed:
        if field_name is None:
            continue
        if field_name == "":
            specs.append("")
            continue
        head = field_name.split(".", 1)[0].split("[", 1)[0]
        if head.isdigit():
            specs.append(head)
        # 具名字段不参与位置字段比较
    return specs


class TaskStringVisitor(ast.NodeVisitor):
    def __init__(self):
        self.strings = []

    def visit_Assign(self, node):
        for target in node.targets:
            self._collect_assignment(target, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        self._collect_assignment(node.target, node.value)
        self.generic_visit(node)

    def visit_AugAssign(self, node):
        self._collect_assignment(node.target, node.value)
        self.generic_visit(node)

    def visit_Call(self, node):
        attr = node.func
        if isinstance(attr, ast.Attribute) and attr.attr == "update":
            if self._is_self_attr_in(attr.value, {"default_config", "config_description"}):
                for arg in node.args:
                    self._collect_dict_strings(arg)
            elif self._is_self_attr_in(attr.value, {"config_type"}):
                for arg in node.args:
                    self._collect_config_type_strings(arg)
        self.generic_visit(node)

    def _collect_assignment(self, target, value):
        if self._is_self_attr_in(target, TASK_STRING_ATTRS):
            self._add_string(value)
        elif self._is_self_attr_in(target, {"default_config", "config_description"}):
            self._collect_dict_strings(value)
        elif self._is_self_attr_in(target, {"config_type"}):
            self._collect_config_type_strings(value)
        elif isinstance(target, ast.Subscript):
            self._collect_subscript_assignment(target, value)

    def _collect_subscript_assignment(self, target, value):
        owner = target.value
        if self._is_self_attr_in(owner, {"default_config", "config_description"}):
            self._add_string(target.slice)
            self._collect_value_strings(value)
        elif self._is_self_attr_in(owner, {"config_type"}):
            self._add_string(target.slice)
            self._collect_config_type_value(value)

    def _is_self_attr_in(self, node, attrs):
        return (
            isinstance(node, ast.Attribute)
            and node.attr in attrs
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
        )

    def _add_string(self, node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.strip()
            if value:
                self.strings.append(value)

    def _collect_dict_strings(self, node):
        if not isinstance(node, ast.Dict):
            return
        for key, value in zip(node.keys, node.values, strict=True):
            self._add_string(key)
            self._collect_value_strings(value)

    def _collect_value_strings(self, node):
        self._add_string(node)
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            for item in node.elts:
                self._collect_value_strings(item)
        elif isinstance(node, ast.Dict):
            self._collect_dict_strings(node)

    def _collect_config_type_strings(self, node):
        if not isinstance(node, ast.Dict):
            return
        for key, value in zip(node.keys, node.values, strict=True):
            self._add_string(key)
            self._collect_config_type_value(value)

    def _collect_config_type_value(self, node):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and key.value in {"options", "buttons"}:
                    self._collect_value_strings(value)
                elif isinstance(key, ast.Constant) and key.value == "text":
                    self._add_string(value)
        elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            for item in node.elts:
                self._collect_config_type_value(item)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value not in CONFIG_TYPE_META:
            self._add_string(node)


def scan_task(path):
    with open(path, encoding="utf-8-sig") as f:
        tree = ast.parse(f.read(), filename=path)
    visitor = TaskStringVisitor()
    visitor.visit(tree)
    for value in dict.fromkeys(visitor.strings):
        print(value)


def iter_po_paths(i18n_dir):
    yield from sorted(Path(i18n_dir).glob("*/LC_MESSAGES/ok.po"))


def entry_key(entry):
    # 重复项判定只依据 (msgctxt, msgid)：同一上下文与源文的条目即使 msgid_plural
    # 不同，也属于目录内的无效重复。复数源文在跨语言目录比较中单独校验。
    return entry.msgctxt, entry.msgid


def entry_key_sort(key):
    context, msgid = key
    return context is not None, context or "", msgid


def translated_strings(entry):
    if entry.msgid_plural:
        return list(entry.msgstr_plural.values())
    return [entry.msgstr]


# 有意保留源语言回退的空 msgstr 标记：在条目注释（tcomment/comment）中包含
# `i18n-fallback`。未带标记的空译文一律判为失败，带标记的视为合法回退。
FALLBACK_MARKER = "i18n-fallback"


def is_intentional_fallback(entry):
    if FALLBACK_MARKER not in (entry.comment or ""):
        return False
    if FALLBACK_MARKER not in (entry.tcomment or ""):
        return False
    return True


def compile_i18n(i18n_dir):
    paths = list(iter_po_paths(i18n_dir))
    if not paths:
        raise SystemExit(f"No ok.po catalogs found under {i18n_dir}")
    for po_path in paths:
        mo_path = po_path.with_name("ok.mo")
        po = polib.pofile(str(po_path))
        po.save_as_mofile(str(mo_path))
        print(f"compiled {po_path} -> {mo_path}")


def check_i18n(i18n_dir):
    paths = list(iter_po_paths(i18n_dir))
    if not paths:
        raise SystemExit(f"No ok.po catalogs found under {i18n_dir}")

    failed = False
    catalog_keys = {}
    catalog_plurals = {}
    for po_path in paths:
        po = polib.pofile(str(po_path))
        locale = po_path.parents[1].name
        entries = [entry for entry in po if entry.msgid and not entry.obsolete]
        keys = [entry_key(entry) for entry in entries]
        duplicates = sorted(
            (key for key, count in Counter(keys).items() if count > 1),
            key=entry_key_sort,
        )
        if duplicates:
            failed = True
            print(f"duplicate entries in {po_path}:")
            for context, msgid in duplicates:
                print(f"  context={context!r} msgid={msgid!r}")

        for entry in entries:
            translations = translated_strings(entry)
            if not translations or any(not translation for translation in translations):
                if is_intentional_fallback(entry):
                    continue
                failed = True
                print(f"empty translation in {po_path}: {entry.msgid!r}")
                continue
            expected_singular = positional_field_specs(entry.msgid)
            expected_plural = expected_singular
            if entry.msgid_plural:
                expected_plural = positional_field_specs(entry.msgid_plural)
            if expected_singular is None or expected_plural is None:
                print(f"skipped placeholder check (unparsable source) in {po_path}: {entry.msgid!r}")
                continue
            expected_sets = {tuple(expected_singular), tuple(expected_plural)}
            for translation in translations:
                actual = positional_field_specs(translation)
                if actual is None:
                    failed = True
                    print(
                        f"placeholder parse error in {po_path}: {entry.msgid!r} "
                        f"translation={translation!r} is not a valid format string"
                    )
                    continue
                if tuple(actual) not in expected_sets:
                    failed = True
                    print(
                        f"placeholder mismatch in {po_path}: {entry.msgid!r} "
                        f"expected={expected_singular} or {expected_plural} "
                        f"actual={actual}"
                    )

        catalog_keys[locale] = set(keys)
        # 单独记录复数源文：重复项判定已不包含 msgid_plural，跨语言比较时再单独校验。
        catalog_plurals[locale] = {
            entry_key(entry): entry.msgid_plural for entry in entries
        }
        if not duplicates:
            print(f"ok {po_path}")

    reference_locale = sorted(catalog_keys)[0]
    reference_keys = catalog_keys[reference_locale]
    reference_plurals = catalog_plurals[reference_locale]
    for locale, keys in sorted(catalog_keys.items()):
        missing = sorted(reference_keys - keys, key=entry_key_sort)
        extra = sorted(keys - reference_keys, key=entry_key_sort)
        if missing or extra:
            failed = True
            print(f"catalog key mismatch for {locale} vs {reference_locale}: missing={len(missing)} extra={len(extra)}")
            for key in missing[:20]:
                print(f"  missing {key}")
            for key in extra[:20]:
                print(f"  extra {key}")
        # 跨语言复数源文比较：同一 key 的 msgid_plural 必须与参考语言一致。
        plural_mismatch = sorted(
            (
                key
                for key in reference_keys & keys
                if reference_plurals.get(key) != catalog_plurals[locale].get(key)
            ),
            key=entry_key_sort,
        )
        if plural_mismatch:
            failed = True
            print(f"plural source mismatch for {locale} vs {reference_locale}: {len(plural_mismatch)}")
            for key in plural_mismatch[:20]:
                print(
                    f"  {key!r} reference={reference_plurals.get(key)!r} "
                    f"actual={catalog_plurals[locale].get(key)!r}"
                )
    if failed:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan")
    scan.add_argument("--task", required=True)

    compile_cmd = subparsers.add_parser("compile")
    compile_cmd.add_argument("--i18n", default="i18n")

    check_cmd = subparsers.add_parser("check")
    check_cmd.add_argument("--i18n", default="i18n")

    args = parser.parse_args()

    if args.command == "scan":
        scan_task(args.task)
    elif args.command == "compile":
        compile_i18n(args.i18n)
    elif args.command == "check":
        check_i18n(args.i18n)


if __name__ == "__main__":
    main()
