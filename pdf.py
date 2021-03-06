import os
import tempfile

from PyPDF2 import PdfFileWriter, PdfFileReader
from PyPDF2.generic import Destination, NullObject
from PyPDF2.utils import PdfReadError
from ricecooker.utils.downloader import read


class CustomDestination(Destination):
    def __init__(self, title, page, typ, *args):
        try:
            super(CustomDestination, self).__init__(title, page, typ, *args)
        except PdfReadError:
            pass

class CustomPDFReader(PdfFileReader):
    def _buildDestination(self, title, array):
        page, typ = array[0:2]
        array = array[2:]
        return CustomDestination(title, page, typ, *array)


class PDFOperationError(Exception):
    pass


class PDFNoTOCError(Exception):
    pass


class PDFParser(object):
    path = None

    def __init__(self, url_or_path, directory="downloads", toc=None):
        """
        Reads and performs editing operations on a PDF file.

        :param url_or_path: Filesystem or URL path of PDF to parse.
        :param directory: Directory to store any downloaded files.
        :param toc: If specified, a Python dictionary listing chapters w/page numbers.
        """
        self.directory = directory
        self.download_url = url_or_path

        # Some PDFs do not have their TOCs set. In that case, we
        # pass a manually created Table of Contents in the same
        # format as generated by the get_toc() method.
        self.toc = toc

    def __enter__(self):
        """ Called when opening context (e.g. with HTMLWriter() as writer: ). """
        self.open()
        return self

    def __exit__(self, type, value, traceback):
        """ Called when closing context. """
        self.close()


    def open(self):
        """
        Opens the specified PDF file for editing. If the path is a URL, it will first download the file.
        """
        filename = os.path.basename(self.download_url)
        folder, _ext = os.path.splitext(filename)
        self.path = os.path.sep.join([self.directory, folder, filename])
        if not os.path.exists(os.path.dirname(self.path)):
            os.makedirs(os.path.dirname(self.path))

        # Download full pdf if it hasn't already been downloaded
        if not os.path.isfile(self.path):
            with open(self.path, "wb") as fobj:
                fobj.write(read(self.download_url))

        self.file = open(self.path, 'rb')
        self.pdf = CustomPDFReader(self.file)

    def close(self):
        """
        Close main pdf file when done.
        """
        self.file.close() # Make sure zipfile closes no matter what

    def check_path(self):
        """
        Checks that there is a local PDF file on disk.

        :raises IOError: If the file cannot be found.
        """
        if not self.path:
            raise IOError("Cannot read file: no path provided (must call `open`)")

    def get_toc(self):
        self.check_path()
        pages = []
        index = 0

        for dest in self.pdf.getOutlines():
            # Only factor in whole chapters, not subchapters (lists)
            if isinstance(dest, CustomDestination) and not isinstance(dest['/Page'], NullObject):
                page_num = self.pdf.getDestinationPageNumber(dest)
                pages.append({
                    "title": dest['/Title'].replace('\xa0', ' '),
                    "page_start": page_num if index != 0 else 0,
                    "page_end": self.pdf.numPages
                })

                # Go back to previous chapter and set page_end
                if index > 0:
                    pages[index - 1]["page_end"] = page_num
                index += 1

        return pages

    def split_chapters(self):
        self.check_path()

        # manually specified TOC always takes precedence
        toc = self.toc
        if toc is None:
            toc = self.get_toc()

        if len(toc) == 0:
            raise PDFNoTOCError("No TOC specified or available for PDF, cannot split chapters.")
        directory = os.path.dirname(self.path)
        chapters = []

        for index, chapter in enumerate(toc):
            writer = PdfFileWriter()
            slug = "".join([c for c in chapter['title'].replace(" ", "-") if c.isalnum() or c == "-"])
            write_to_path = os.path.sep.join([directory, "{}.pdf".format(slug)])

            for page in range(chapter['page_start'], chapter['page_end']):
                writer.addPage(self.pdf.getPage(page))

            with open(write_to_path, 'wb') as outfile:
                writer.write(outfile)
            chapters.append({"title": chapter['title'], "path": write_to_path})

        return chapters
