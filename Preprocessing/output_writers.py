
import csv
import os

WORKS_FILENAME = "Works_AI_Only.tsv"
AUTHOR_INSTITUTION_FILENAME = "Works_Authors_Institutions_AI.tsv"
ALTERNATE_SOURCE_FILENAME = "Works_Alternate_Sources_AI.tsv"

works_fields = [
    'id', 'doi', 'publication_year', 'language', 'title', 'abstract',
    'primary_location_source_id', 'primary_location_source_display_name',
    'primary_location_source_type', 'primary_location_source_issn',
    'primary_location_source_issn_l', 'type', 'type_crossref',
    'countries_distinct_count', 'institutions_distinct_count',
    'cited_by_count', 'locations_count', 'classification', 'score',
]
work_author_institution_fields = [
    'work_id', 'author_position', 'author_id',
    'institution_id', 'institution_type', 'institution_country',
]
work_alternate_source_fields = [
    'work_id', 'source_id', 'source_type', 'source_issn', 'source_issn_l',
]


class OutputWriters:

    def __init__(self, output_dir, append=False):
        self.output_dir = output_dir
        self.append = append
        self._files = []

        self.works = None
        self.author_institution = None
        self.alternate_source = None

    def _open_writer(self, filename, fieldnames):
        mode = 'a' if self.append else 'w'
        path = os.path.join(self.output_dir, filename)
        need_header = not self.append or not os.path.exists(path) or os.path.getsize(path) == 0

        handle = open(path, mode, encoding='utf-8', newline='')
        self._files.append(handle)

        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter='\t', extrasaction='ignore')
        if need_header:
            writer.writeheader()
        return writer

    def __enter__(self):
        os.makedirs(self.output_dir, exist_ok=True)
        self.works = self._open_writer(WORKS_FILENAME, works_fields)
        self.author_institution = self._open_writer(
            AUTHOR_INSTITUTION_FILENAME, work_author_institution_fields)
        self.alternate_source = self._open_writer(
            ALTERNATE_SOURCE_FILENAME, work_alternate_source_fields)
        return self

    def flush(self):
        for handle in self._files:
            handle.flush()

    def close(self):
        for handle in self._files:
            try:
                handle.close()
            except Exception as e:
                print(f"error closing output file: {e}")
        self._files = []

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False
