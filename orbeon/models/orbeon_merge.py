# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from bs4 import BeautifulSoup

NO_COPY_PREFIX_DEFAULT = "NC."
SKIP_TAGS_DEFAULT = {"annotation", "image"}


def _is_leaf(tag):
    """Return True if the tag has no element-children (ok to set .string safely)."""
    if not tag:
        return False
    return tag.find(True) is None  # no child elements


def merge_runner_into_builder_xml_bs(
    runner_xml: str,
    builder_xml: str,
    *,
    no_copy_prefix: str = NO_COPY_PREFIX_DEFAULT,
    skip_tags=frozenset(SKIP_TAGS_DEFAULT),
) -> str:
    """
    Merge text values from runner_xml into builder_xml using BeautifulSoup.
    - Only copies text into matching *tag names*.
    - Skips tags with names starting with `no_copy_prefix` (e.g., "NC.").
    - Skips tags in `skip_tags` (e.g., 'annotation', 'image').
    - Operates primarily on the <form> under id="fr-form-instance" if present;
      otherwise falls back to the first <form> found.
    - Copies only into LEAF elements to avoid clobbering nested content.
    Returns the *entire* modified builder document as a string.
    """
    if not builder_xml:
        return builder_xml or ""

    # Parse both documents as XML
    b_soup = BeautifulSoup(builder_xml or "", "lxml-xml")
    r_soup = BeautifulSoup(runner_xml or "", "lxml-xml")

    # Find <form> scope in builder (same as old XPath //*[@id='fr-form-instance']/form)
    instance = b_soup.find(attrs={"id": "fr-form-instance"})
    if instance:
        # try direct child <form> first, then any descendant <form>
        form = next((c for c in instance.find_all("form", recursive=False)), None) or instance.find("form")
    else:
        form = b_soup.find("form")

    if not form:
        # Nothing to merge into
        return str(b_soup)

    # Walk all elements inside the target <form>
    for el in form.find_all(True):  # True => any tag
        tag_name = el.name or ""
        if not tag_name:
            continue

        # Skip special tags and no-copy tags
        if tag_name in skip_tags:
            continue
        if no_copy_prefix and tag_name.startswith(no_copy_prefix):
            continue

        # Find first occurrence in the runner by tag name (mirrors //tag behavior)
        src = r_soup.find(tag_name)
        if not src:
            continue

        # Pull source text if it exists and is non-empty
        src_text = (src.get_text() or "").strip()
        if not src_text:
            continue

        # Only write into leaf nodes to avoid destroying structure
        if _is_leaf(el):
            el.string = src_text
        else:
            # If it's not a leaf, we mimic the old ".text" copy lightly:
            # Only replace the direct text content, leave children intact.
            # (If you want strict parity with old code, you can force set .string,
            # but that's risky when a node has children.)
            if el.contents and isinstance(el.contents[0], str):
                el.contents[0].replace_with(src_text)
            elif not el.contents:
                el.string = src_text
            # Otherwise, leave as-is (has element-children).

    return str(b_soup)

class OrbeonRunner(models.Model):
    _inherit = "orbeon.runner"
    _description = "Orbeon Runner"

    is_merged = fields.Boolean(default=False)

    @api.returns("self")
    def merge_builder_bs(self, builder_obj, no_copy_prefix=NO_COPY_PREFIX_DEFAULT):
        """
        Merge this Runner's text values into the given builder_obj.xml using BeautifulSoup,
        then write the merged XML back onto this Runner and relink to builder_obj.
        """
        self.ensure_one()
        if not builder_obj or not builder_obj.xml:
            raise UserError(_("No builder or empty builder XML was provided."))

        merged_xml = merge_runner_into_builder_xml_bs(
            runner_xml=self.xml or "",
            builder_xml=builder_obj.xml or "",
            no_copy_prefix=no_copy_prefix or "",
            skip_tags=SKIP_TAGS_DEFAULT,
        )

        self.write(
            {
                "xml": merged_xml,
                "builder_id": builder_obj.id,
                "is_merged": True,
            }
        )
        return self
