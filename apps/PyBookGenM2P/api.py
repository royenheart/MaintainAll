from enum import Enum

import aspose.words as aw
import pypandoc
from md2pdf.core import md2pdf


class m2p_apis(Enum):
    ASPOSE = 1
    MD2PDF = 2
    PYPANDOC = 3


class m2p:
    def __init__(self, inF, outF, api,
                 pandoc_internal=False):
        self.inF = inF
        self.outF = outF
        self.api = api
        self.pandoc_internal = pandoc_internal
        self.funcs = {
            m2p_apis.ASPOSE: self.apose,
            m2p_apis.MD2PDF: self.md2pdf,
            m2p_apis.PYPANDOC: self.pandoc
        }

    def convert(self):
        method = self.funcs.get(self.api, self.NoMethod)
        if method:
            ret = method()
            return ret
        return "No Such API"

    def apose(self):
        """
        Use Aspose.Words for Python via .NET(https://products.aspose.com/words/zh/python-net/) to convert
        """
        try:
            doc = aw.Document(self.inF)
            doc.save(self.outF)
        except:
            print("{} to {} not generated successfully!", self.inF, self.outF)
            exit(RuntimeError)
        return "Successfully convert {} to {}!".format(self.inF, self.outF)

    def md2pdf(self):
        """
        Use md2pdf(https://github.com/jmaupetit/md2pdf) to convert
        """
        try:
            md2pdf(pdf_file_path=self.outF,
                   md_file_path=self.inF)
        except:
            print("{} to {} not generated successfully!", self.inF, self.outF)
            exit(RuntimeError)
        return "Successfully convert {} to {}!".format(self.inF, self.outF)

    def pandoc(self):
        """
        Use PyPandoc(https://github.com/JessicaTegner/pypandoc) to convert
        You need to install an available installation of pandoc first
        """
        if self.pandoc_internal:
            from pypandoc.pandoc_download import download_pandoc
            download_pandoc()
        output = pypandoc.convert_file(source_file=self.inF,
                                       to='pdf',
                                       format='md',
                                       outputfile=self.outF)
        assert output == ""
        return "Successfully convert {} to {}!".format(self.inF, self.outF)

    def NoMethod(self):
        raise ModuleNotFoundError("m2p has no such api: {}".format(self.api))


def markdown_to_pdf(inF, outF, api=m2p_apis.ASPOSE, pandoc_internal=False):
    m2p_obj = m2p(inF, outF, api, pandoc_internal)
    ret = m2p_obj.convert()
    return ret
