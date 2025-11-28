from odoo import api, fields, models, _
from odoo.exceptions import UserError
from bs4 import BeautifulSoup, Tag
import difflib
import logging
_logger = logging.getLogger(__name__)

KEY_ATTRS = ("id", "name", "ref", "bind")

class OrbeonRunner(models.Model):
    _inherit = "orbeon.runner"
    _description = "Orbeon Runner"

    is_merged = fields.Boolean(default=False)

    @api.model
    def _build_runner_index(self, root: Tag):
        """Global index of runner elements by key."""
        index = {}
        for el in root.find_all():
            k = self._child_key(el)
            if not k:
                continue
            index.setdefault(k, []).append(el)
        return index

    @api.model
    def _control_key(self, el: Tag):
        if not getattr(el, "name", None):
            return None
        return el.get("id") or el.get("ref") or el.get("bind")

    @api.model
    def _is_control(self, el: Tag):
        if not getattr(el, "name", None):
            return False
        return bool(el.get("id") or el.get("ref") or el.get("bind"))

    @api.model
    def _normalize_xml(self, el: Tag) -> str:
        el_copy = BeautifulSoup(str(el), "xml").find(el.name)
        if el_copy and el_copy.attrs:
            attrs_sorted = dict(sorted(el_copy.attrs.items()))
            el_copy.attrs.clear()
            el_copy.attrs.update(attrs_sorted)
        return el_copy.decode() if el_copy else ""

    @api.model
    def _index_controls(self, soup: BeautifulSoup):
        index = {}
        for el in soup.find_all():
            if not self._is_control(el):
                continue
            k = self._control_key(el)
            if not k:
                continue
            index[k] = el
        return index

    @api.model
    def _compare_builder_xml(self, builder_old: str, builder_new: str, with_details=False):
        s_old = BeautifulSoup(builder_old or "", "xml")
        s_new = BeautifulSoup(builder_new or "", "xml")
    
        idx_old = self._index_controls(s_old)
        idx_new = self._index_controls(s_new)
    
        keys_old = set(idx_old.keys())
        keys_new = set(idx_new.keys())
    
        added = sorted(keys_new - keys_old)
        removed = sorted(keys_old - keys_new)
        common = keys_old & keys_new
    
        changed = []
        unchanged = []
        details = {}
    
        for k in sorted(common):
            old_norm = self._normalize_xml(idx_old[k])
            new_norm = self._normalize_xml(idx_new[k])
            if old_norm == new_norm:
                unchanged.append(k)
            else:
                changed.append(k)
                if with_details:
                    diff_lines = difflib.unified_diff(
                        old_norm.splitlines(),
                        new_norm.splitlines(),
                        fromfile=f"old:{k}",
                        tofile=f"new:{k}",
                        lineterm="",
                    )
                    details[k] = "\n".join(diff_lines)
    
        result = {
            "added": added,
            "removed": removed,
            "changed": changed,
            "unchanged": unchanged,
        }
        if with_details:
            result["details"] = details
    
        return result

    @api.model
    def _get_builder_instance_root(self, soup: BeautifulSoup,
                                   instance_id="fr-form-instance") -> Tag:
        inst = (soup.find("xf:instance", {"id": instance_id}) or
                soup.find("instance", {"id": instance_id}))
        if not inst:
            raise UserError(_("Instance with id='%s' not found in builder XML") % instance_id)

        for child in inst.children:
            if getattr(child, "name", None):
                return child

        raise UserError(_("Instance '%s' has no element root in builder XML") % instance_id)

    @api.model
    def _get_runner_root(self, soup: BeautifulSoup) -> Tag:
        for child in soup.contents:
            if getattr(child, "name", None):
                return child
        raise UserError(_("Runner XML has no root element"))

    @api.model
    def _child_key(self, el: Tag):
        if not getattr(el, "name", None):
            return None
        return (el.name,) + tuple(el.get(a) for a in KEY_ATTRS)

    @api.model
    def _merge_elements(self, runner_el: Tag, builder_el: Tag, runner_index: dict):
        for attr_name, attr_val in builder_el.attrs.items():
            if attr_name not in runner_el.attrs:
                runner_el[attr_name] = attr_val
    
        existing = {}
        for child_r in runner_el.find_all(recursive=False):
            k = self._child_key(child_r)
            if k is not None:
                existing.setdefault(k, []).append(child_r)
    
        for child_b in builder_el.find_all(recursive=False):
            if not getattr(child_b, "name", None):
                continue
    
            k = self._child_key(child_b)
            if k is None:
                continue
    
            child_r = None
    
            candidates = existing.get(k) or []
            if candidates:
                child_r = candidates.pop(0)
            else:
                global_candidates = runner_index.get(k) or []
                if global_candidates:
                    child_r = global_candidates.pop(0)
                    child_r.extract()
    
            if child_r is None:
                frag = BeautifulSoup(str(child_b), "xml")
                cloned = frag.find(child_b.name)
                if not cloned:
                    continue
    
                for sub in list(cloned.find_all(recursive=False)):
                    sub.extract()
    
                child_r = cloned
                runner_el.append(child_r)
            else:
                if child_r.parent is not runner_el:
                    runner_el.append(child_r)
    
            self._merge_elements(child_r, child_b, runner_index)

    @api.model
    def _merge_runner_with_builder(self, runner_xml: str, builder_xml: str,
                                   instance_id: str = "fr-form-instance") -> str:
        s_runner = BeautifulSoup(runner_xml or "", "xml")
        s_builder = BeautifulSoup(builder_xml or "", "xml")

        runner_root = self._get_runner_root(s_runner)
        builder_root = self._get_builder_instance_root(s_builder, instance_id=instance_id)

        runner_index = self._build_runner_index(runner_root)

        self._merge_elements(runner_root, builder_root, runner_index)

        return str(s_runner)

    def merge_current_builder(self):
        """
        For this runner:
        - Get its builder (old builder)
        - Find the 'current' builder in the same tree
        - If different:
            * Compare old vs current builder XML (for logging)
            * Merge runner XML to match current builder instance structure
        """
        self.ensure_one()

        if not self.builder_id or not self.builder_id.xml:
            raise UserError(_("No builder XML linked to this runner."))

        old_builder = self.builder_id

        all_versions = self.env['orbeon.builder'].search([
            ('parent_id', 'child_of', self.builder_id.id)
        ])
        _logger.debug("all_versions for builder %s: %s", self.builder_id.id, all_versions.ids)

        current_version = all_versions.filtered(lambda x: x.state == 'current')[:1]
        if current_version:
            _logger.debug("current_version for builder %s: %s", self.builder_id.id, current_version.ids)

            if current_version.id != self.builder_id.id:
                diff = self._compare_builder_xml(old_builder.xml, current_version.xml, with_details=True)
                _logger.info(
                    "Builder diff for runner %s (old builder %s -> current builder %s): "
                    "added=%s, removed=%s, changed=%s",
                    self.id, old_builder.id, current_version.id,
                    diff["added"], diff["removed"], diff["changed"],
                )
            
            for key, text_diff in (diff.get("details") or {}).items():
                _logger.info("XML diff for control '%s':\n%s", key, text_diff)
                merged_runner_xml = self._merge_runner_with_builder(
                    self.xml or "",
                    current_version.xml or "",
                    instance_id="fr-form-instance",
                )

                self.write({
                    "xml": merged_runner_xml,
                    "builder_id": current_version.id,
                    "is_merged": True,
                })

        return True
