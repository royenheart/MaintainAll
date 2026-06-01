# -*- coding: utf-8 -*-
import copy
import os
import shutil

import PyPDF2 as pypdf

from api import markdown_to_pdf, m2p_apis

mdLists = {}
fileLists = []
folderLists = []


def Combine(docs, out):
    """
    Combine specified pdfs to one pdf
    """
    tmpFile = []
    tmpReader = []
    writer = pypdf.PdfFileWriter()
    for name in docs:
        openDoc = open(name, 'rb')
        tmpFile.append(openDoc)
        tmpReader.append(pypdf.PdfFileReader(openDoc))
    for reader in tmpReader:
        for pageIndex in range(reader.numPages):
            writer.addPage(reader.getPage(pageIndex))
    writer.write(out)
    for file in tmpFile:
        file.close()


def GetFiles(srcDirs):
    """
    Get source dir files
    mdLists - store markdowns need to be compiled and combined
    fileLists - store file markdown compile need
    folderLists - store folders markdown compile need
    """
    for curDir, dirs, files in os.walk(srcDirs):
        chapter = curDir.replace("\\", "-").replace(srcDirs, "")
        assetMDs = []
        assetFiles = copy.deepcopy(files)
        for file in files:
            if file.endswith(".md"):
                assetMDs.append(os.path.join(curDir, file))
                assetFiles.remove(file)
        if len(assetMDs) != 0:
            mdLists.setdefault(chapter, assetMDs)
            assetDirs = copy.deepcopy(dirs)
            # delete markdown files
            assetFiles = [os.path.join(curDir, x) for x in assetFiles]
            assetDirs = [os.path.join(curDir, x) for x in assetDirs]
            for assetFile in assetFiles:
                fileLists.append(assetFile)
            for assetDir in assetDirs:
                folderLists.append(assetDir)


def ToPDF(outDir, bookName="defaults.pdf", api=m2p_apis.ASPOSE, rm_temp_file=True):
    # bookName = "{}/{}.pdf".format(outDir, bookName)
    bookName = os.path.join(outDir, "{}.pdf".format(bookName))
    chapterFNs = []
    for chapter, pos in mdLists.items():
        # chapter name
        # chapterFN = "{}/{}.pdf".format(outDir, chapter)
        chapterFN = os.path.join(outDir, "{}.pdf".format(chapter))
        chapterFNs.append(chapterFN)
        # section generate
        tmpFNs = []
        for file, i in zip(pos, range(len(pos))):
            # tmpFN = "{}/{}-{}.pdf".format(outDir, chapter, i)
            tmpFN = os.path.join(outDir, "{}-{}.pdf".format(chapter, i))
            tmpFNs.append(tmpFN)
            ret = markdown_to_pdf(file, tmpFN, api)
            if __debug__:
                print(ret)
        Combine(tmpFNs, chapterFN)
        if rm_temp_file:
            DelFiles(tmpFNs)
    # book generate
    Combine(chapterFNs, bookName)
    if rm_temp_file:
        DelFiles(chapterFNs)
    print("File generated to {}".format(bookName))


def DelFiles(files):
    for file in files:
        os.remove(file)


def CopyFiles(outDir):
    # copy relative assets to folder
    for assetFile in fileLists:
        shutil.copy(assetFile, outDir)
    for assetFolder in folderLists:
        dst = os.path.join(outDir, os.path.basename(assetFolder))
        os.makedirs(dst, exist_ok=True)
        shutil.copytree(assetFolder, dst, dirs_exist_ok=True)


GetFiles(srcDirs="tests")
ToPDF(outDir="out", bookName="Test", api=m2p_apis.ASPOSE, rm_temp_file=True)
CopyFiles(outDir="out")
