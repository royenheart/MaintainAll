# PyBookGenM2P

## What is it

Use to automatically convert your book written in markdown to one pdf file.

You should organize your book structure as example:

```shell
source dir
├─ch01
│  ├─1.1
│  │  └─1.1.md
│  └─1.2
│      └─1.2.md
└─ch02
   ├─2.1
   │  ├─2.1.md
   │  ├─something.js
   │  └─assets(folder)
   └─2.2
       └─2.2.md
```

Links in the document should be relative to the document's parent directory.
