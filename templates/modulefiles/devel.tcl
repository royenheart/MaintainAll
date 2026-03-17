#%Module -*- tcl -*-
# 开发/编译工具模板（-devel）
# 在运行时路径基础上，追加头文件路径和编译标志
# 占位符由 manage_modules.py 替换：NAME VERSION INSTALL_PATH

set NAME    "{{ NAME }}"
set VERSION "{{ VERSION }}"
set SPATH   {{ INSTALL_PATH }}

proc ModulesHelp { } {
    global NAME VERSION
    puts stderr "$NAME $VERSION (devel)"
}

module-whatis "$NAME $VERSION (devel)"

conflict $NAME-devel

prepend-path  C_INCLUDE_PATH    $SPATH/include
prepend-path  CXX_INCLUDE_PATH  $SPATH/include
prepend-path  LD_LIBRARY_PATH   $SPATH/lib
prepend-path  LD_LIBRARY_PATH   $SPATH/lib64
prepend-path  PKG_CONFIG_PATH   $SPATH/lib/pkgconfig
prepend-path  PKG_CONFIG_PATH   $SPATH/lib64/pkgconfig

prepend-path  --delim " "  CFLAGS    -I$SPATH/include
prepend-path  --delim " "  CXXFLAGS  -I$SPATH/include
prepend-path  --delim " "  FFLAGS    -I$SPATH/include
prepend-path  --delim " "  FCFLAGS   -I$SPATH/include
prepend-path  --delim " "  LDFLAGS   -L$SPATH/lib
prepend-path  --delim " "  LDFLAGS   -L$SPATH/lib64
