#%Module -*- tcl -*-
# 通用软件包模板
# 设置 PATH、LD_LIBRARY_PATH、PKG_CONFIG_PATH、CMAKE_PREFIX_PATH
# 占位符由 manage_modules.py 替换：NAME VERSION INSTALL_PATH

set NAME    "{{ NAME }}"
set VERSION "{{ VERSION }}"
set SPATH   {{ INSTALL_PATH }}

proc ModulesHelp { } {
    global NAME VERSION
    puts stderr "$NAME $VERSION"
}

module-whatis "$NAME $VERSION"

conflict $NAME

prepend-path  PATH              $SPATH/bin
prepend-path  LD_LIBRARY_PATH   $SPATH/lib
prepend-path  LD_LIBRARY_PATH   $SPATH/lib64
prepend-path  PKG_CONFIG_PATH   $SPATH/lib/pkgconfig
prepend-path  PKG_CONFIG_PATH   $SPATH/lib64/pkgconfig
prepend-path  CMAKE_PREFIX_PATH $SPATH
