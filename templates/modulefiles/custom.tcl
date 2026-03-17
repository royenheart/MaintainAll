#%Module -*- tcl -*-
# 自定义模板
# CUSTOM_ENTRIES 占位符会被替换为用户指定的 prepend-path / setenv 行块
# 每行格式（kvlist 输入）：
#   VAR=/some/path            → prepend-path VAR /some/path
#   setenv VAR=value          → setenv VAR value
#   prepend VAR=/some/path    → prepend-path VAR /some/path
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

{{ CUSTOM_ENTRIES }}
