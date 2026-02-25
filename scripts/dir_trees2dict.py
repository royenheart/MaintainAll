from typing import Callable, Dict, Tuple, Optional, List
import os


def dirTrees2Dict(
    text: str, key_parse: Optional[Callable[[str], Tuple[str, Dict]]] = None
) -> Dict:
    level = -2
    stack: List[List[Tuple[str, Dict]]] = []
    result = {}
    stack.append([("forest", result)])
    text = os.linesep.join([s for s in text.splitlines() if s])
    for t in text.strip().splitlines():
        clevel = t.find("─ ")
        k = t[clevel + 1 :].strip()
        v = {}
        if key_parse:
            k, v = key_parse(k)
        if clevel > level:
            level = clevel
            stack.append([(k, v)])
        elif clevel == level:
            stack[-1].append((k, v))
        else:
            level = clevel
            childs = stack.pop()
            parent_name, parent_v = stack[-1].pop()
            for c in childs:
                n, uv = c
                if "childrens" in parent_v:
                    parent_v["childrens"].update({n: uv})
                else:
                    parent_v["childrens"] = {n: uv}
            stack[-1].append((parent_name, parent_v))
            stack[-1].append((k, v))
    while len(stack) > 1:
        childs = stack.pop()
        parent_name, parent_v = stack[-1].pop()
        for c in childs:
            n, uv = c
            if "childrens" in parent_v:
                parent_v["childrens"].update({n: uv})
            else:
                parent_v["childrens"] = {n: uv}
        stack[-1].append((parent_name, parent_v))
    _, f = stack.pop()[-1]
    return f["childrens"]


if __name__ == "__main__":
    import pprint

    data1 = """
    Bad Speculation                             6.10    --
    ├── Branch Mispredicts                      5.75    br_mis_pred
    │   ├── Indirect Branch                     0.01    --
    │   ├── Push Branch                         0.00    --
    │   ├── Pop Branch                          0.00    --
    │   └── Other Branch                        5.74    --
    └── Machine Clears                          0.35    --
        ├── Nuke Flush                          0.12    --
        └── Other Flush                         0.22    --

    Frontend Bound                             23.45    fetch_bubble
    ├── Fetch Latency Bound                    17.21    --
    │   ├── ITLB Miss                           1.29    --
    │   │   ├── L1 Tlb                          1.23    --
    │   │   └── L2 Tlb                          0.06    l2i_tlb_refill
    │   ├── ICache Miss                         8.64    --
    │   │   ├── L1 Cache                        4.30    --
    │   │   └── L2 Cache                        4.34    l2i_cache_refill
    │   ├── Branch Mispredict Flush             2.75    br_mis_pred
    │   ├── OoO Flush                           0.16    --
    │   └── Static Predictor Flush              0.50    --
    └── Fetch Bandwidth Bound                   6.23    --

    Retiring                                   58.63    inst_retired

    Backend Bound                              11.81    --
    ├── Resource Bound                          0.42    --
    │   ├── Sync Stall                          0.00    --
    │   ├── Reorder Buffer Stall                0.03    --
    │   ├── Physical Tag Stall                  0.17    --
    │   ├── SaveOp Queue Stall                  0.00    --
    │   ├── PC Buffer Stall                     0.07    --
    │   └── Other Stall                         0.14    --
    ├── Core Bound                              9.43    --
    │   ├── Divider Stall                       0.00    --
    │   ├── FSU Stall                           0.00    --
    │   └── Exe Ports Util                      9.42    --
    │       ├── ALU BRU IssueQ Full             0.16    --
    │       ├── LS IssueQ Full                  0.47    --
    │       └── FSU IssueQ Full                 0.00    --
    └── Memory Bound                            1.95    --
        ├── L1 Bound                            1.34    --
        ├── L2 Bound                            0.07    --
        ├── L3 or DRAM Bound                    0.48    cache-misses
        └── Store Bound                         0.04    --
    """

    data2 = """
    .
    ├── ASTnode_coding
    │   └── README.md
    ├── data
    │   ├── all_clone_pair.csv
    │   ├── clone-pair-270000(noT4).csv
    │   ├── id2sourcecode
    │   ├── IJaDataset100k
    │   ├── IJaDataset10k
    │   ├── IJaDataset10M
    │   ├── IJaDataset1M
    │   └── noclone-pair.csv
    ├── depracated
    │   └── finals-1.0-SNAPSHOT.jar
    ├── finals-1.0-SNAPSHOT.jar
    ├── README.md
    ├── sourcecode
    │   ├── dependency-reduced-pom.xml
    │   ├── pom.xml
    │   ├── src
    │   └── target
    └── supplementary_experiment
        └── readme2.md
    """

    def parse_topdown_line(l: str):
        l = (" ".join(l.split())).rsplit(" ", maxsplit=2)
        return (l[0], {"rate": l[1], "event": l[2]})

    result1 = dirTrees2Dict(text=data1, key_parse=parse_topdown_line)
    pprint.pprint(result1)

    result2 = dirTrees2Dict(data2)
    pprint.pprint(result2)
