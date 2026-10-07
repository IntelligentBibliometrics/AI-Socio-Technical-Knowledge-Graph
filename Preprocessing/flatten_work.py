
import json

work_prefix = "https://openalex.org/W"
author_prefix = "https://openalex.org/A"
institution_prefix = "https://openalex.org/I"
source_prefix = "https://openalex.org/S"


def check_issn_match(issn_value, ai_issn_set):
    if not issn_value:
        return False

    if isinstance(issn_value, list):
        return any(str(issn).strip() in ai_issn_set for issn in issn_value if issn)
    if isinstance(issn_value, str):
        return issn_value.strip() in ai_issn_set
    return False


def is_ai_paper(work, ai_issn_set):
    # A work is kept only if the ISSN of its primary_location (the publisher's
    # version of record) is on the AI-journal list. Other locations (preprint
    # servers, institutional repositories, metadata records) are not consulted
    # and never create additional paper nodes or venue links.
    if primary_location := work.get('primary_location'):
        if primary_source := primary_location.get('source'):
            if (check_issn_match(primary_source.get('issn'), ai_issn_set)
                    or check_issn_match(primary_source.get('issn_l'), ai_issn_set)):
                return True

    return False


def _format_issn(value):
    return str(value) if value else None


def _write_works_row(work, work_id, writer):
    work['id'] = work_id

    if primary_location := work.get('primary_location'):
        if primary_source := primary_location.get('source'):
            source_id = primary_source.get('id') or ''
            work['primary_location_source_id'] = source_id.replace(source_prefix, '')
            work['primary_location_source_display_name'] = primary_source.get('display_name')
            work['primary_location_source_type'] = primary_source.get('type')
            work['primary_location_source_issn'] = _format_issn(primary_source.get('issn'))
            work['primary_location_source_issn_l'] = _format_issn(primary_source.get('issn_l'))

    if (abstract := work.get('abstract_inverted_index')) is not None:
        work['abstract'] = json.dumps(abstract, ensure_ascii=False)

    writer.writerow(work)


def _write_author_institution_rows(work, work_id, writer):
    for authorship in work.get('authorships') or []:
        author = authorship.get('author') or {}
        author_id = author.get('id')
        if not author_id:
            continue

        author_position = authorship.get('author_position')
        author_id = author_id.replace(author_prefix, '')
        institutions = authorship.get('institutions') or []

        if institutions:
            for institution in institutions:
                institution_id = institution.get('id')
                writer.writerow({
                    'work_id': work_id,
                    'author_position': author_position,
                    'author_id': author_id,
                    'institution_id': institution_id.replace(institution_prefix, '') if institution_id else None,
                    'institution_type': institution.get('type'),
                    'institution_country': institution.get('country_code'),
                })
        else:
            writer.writerow({
                'work_id': work_id,
                'author_position': author_position,
                'author_id': author_id,
                'institution_id': None,
                'institution_type': None,
                'institution_country': None,
            })


def _write_alternate_source_rows(work, work_id, writer):
    for location in work.get('locations') or []:
        source = location.get('source')
        if not source or not source.get('id'):
            continue
        writer.writerow({
            'work_id': work_id,
            'source_id': source['id'].replace(source_prefix, ''),
            'source_type': source.get('type'),
            'source_issn': _format_issn(source.get('issn')),
            'source_issn_l': _format_issn(source.get('issn_l')),
        })


def organize(work, writers, ai_issn_set=None):
    work_id = work.get('id')
    if not work_id:
        return False

    if ai_issn_set is not None and not is_ai_paper(work, ai_issn_set):
        return False

    work_id = work_id.replace(work_prefix, '')

    _write_works_row(work, work_id, writers.works)
    _write_author_institution_rows(work, work_id, writers.author_institution)
    _write_alternate_source_rows(work, work_id, writers.alternate_source)

    return True
