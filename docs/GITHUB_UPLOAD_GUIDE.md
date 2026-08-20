# GitHub Desktop Upload Guide — No Git LFS

This package is prepared for a **GitHub Desktop–first workflow**. You do not need Git LFS and you do not need to use the command line for normal publication.

The largest supplied file is the original demonstration video:

- `original_submission/NE_Phase_002_Sepehr_Rajabi/NE_Video.mp4`
- size: **56,326,921 bytes (~53.7 MiB)**

GitHub currently warns when a normal Git file is larger than **50 MiB**, but the push can still succeed; files larger than **100 MiB** are blocked. Because this video is about **53.7 MiB**, you may see a large-file warning, but it remains below the hard limit. The repository therefore stores the MP4 and PCAPNG evidence as normal Git files, exactly as requested.

> Important: future replacement videos or packet captures must also remain below GitHub's ordinary Git per-file limit if you want to continue avoiding Git LFS.

## 1. Download and extract the ZIP

Extract the complete ZIP to a normal local folder, for example:

```text
Documents/Network_Multicast_Two_Phase_Project/
```

After extraction, the repository root should directly contain items such as:

```text
README.md
src/
docs/
configs/
evidence/
original_submission/
.github/
.gitignore
.gitattributes
CITATION.cff
```

Do not move individual files out of this folder. The relative links in the README and documentation assume this structure.

## 2. Install and sign in to GitHub Desktop

1. Install **GitHub Desktop** from GitHub's official website.
2. Launch GitHub Desktop.
3. Sign in to the GitHub account where you want the academic repository to live.
4. Complete any authentication prompts shown by GitHub Desktop.

GitHub Desktop provides the Git commit/publish workflow through its graphical interface, so a separate terminal workflow is not required for this package.

## 3. Add the extracted project to GitHub Desktop

This ZIP contains an intentionally initialized local Git repository with branch `main`, but **no author commit has been created for you**. This lets your own GitHub identity author the initial academic commit.

In GitHub Desktop:

1. Select **File → Add Local Repository…**.
2. Click **Choose…**.
3. Select the extracted `Network_Multicast_Two_Phase_Project` folder itself — the folder containing `README.md`.
4. Click **Add Repository**.

You should now see the repository in GitHub Desktop and its project files listed in the **Changes** view.

## 4. Review the initial changes before committing

Before creating the first commit, verify that GitHub Desktop lists the expected repository content, including:

- `README.md`
- `src/phase1/sender.py`
- `src/phase1/receiver.py`
- `src/phase2/mcast_canvas.py`
- `configs/routeros/`
- `docs/`
- `docs/images/`
- `evidence/captures/Wireshark.pcapng`
- both original PDF reports
- the original command note
- the original Wireshark capture
- `NE_Video.mp4`
- the three original Python source files
- `.github/workflows/repository-check.yml`
- `CITATION.cff`

The complete preservation copy remains under `original_submission/` so none of the supplied academic work is lost.

## 5. Create the initial commit in GitHub Desktop

At the lower-left of the GitHub Desktop window:

1. In **Summary (required)**, enter:

```text
Initial academic release: two-stage multicast networking project
```

2. Optionally enter this description:

```text
Preserves the complete two-stage submission and adds a structured, reproducible GitHub-facing layout with source code, RouterOS configurations, documentation, evidence, figures, integrity checks, and academic citation metadata.
```

3. Ensure all intended files are checked in the Changes list.
4. Click **Commit to main**.

The initial commit is now created locally under your own Git identity.

## 6. Publish directly from GitHub Desktop

After the commit, click **Publish repository** in GitHub Desktop.

Use these suggested values:

**Name**

```text
multicast-networking-igmp-pim-shared-canvas
```

**Description**

```text
Two-stage GNS3/RouterOS multicast project: IGMP Proxy, Scapy validation, PIM-SM, and a shared UDP multicast canvas.
```

Then:

1. Select your personal account or organization as the owner.
2. Keep **Keep this code private** selected for the first publication unless you have already reviewed the privacy considerations below.
3. Click **Publish Repository**.

GitHub Desktop will push the complete ordinary-Git repository, including the approximately 53.7 MiB video, without Git LFS.

## 7. Open and verify the repository on GitHub

In GitHub Desktop, choose **Repository → View on GitHub**.

On the GitHub website, confirm that:

- the README renders on the repository home page;
- the topology and evidence images render in the documentation;
- `src/phase1/` contains the sender and receiver;
- `src/phase2/` contains the shared multicast canvas;
- the RouterOS configurations are under `configs/routeros/`;
- both reports are present under `original_submission/`;
- `NE_Video.mp4` appears under the preserved Phase 2 submission folder;
- `Wireshark.pcapng` is present;
- the **Actions** tab contains the `Repository Check` workflow;
- GitHub recognizes `CITATION.cff` and can expose **Cite this repository**.

## 8. Recommended privacy review before making it public

The preservation directory intentionally contains the original academic submission without deleting supplied material. Before changing the repository from Private to Public, review:

- both PDF reports;
- the demonstration video;
- the Wireshark capture;
- topology screenshots and interface labels;
- student names or university identifiers;
- hostnames and IP addressing visible in evidence.

If any of those should not be public, keep this complete repository Private and create a separate redacted public edition later. Do not delete material from this archival package merely to make it public.

## 9. Recommended repository presentation settings

After publication, open the repository's **About** area on GitHub and consider adding these topics:

```text
multicast
igmp
igmp-proxy
pim-sm
gns3
mikrotik
routeros
scapy
wireshark
udp
computer-networks
python
```

Keep `main` as the default branch. Enable Issues only if you want feedback or collaboration. A license has intentionally not been imposed because reuse/licensing is an author decision.

## 10. Making later changes with GitHub Desktop

For future edits:

1. Modify files normally on your computer.
2. Open GitHub Desktop.
3. Review the changed files under **Changes**.
4. Enter a clear commit summary.
5. Click **Commit to main**.
6. Click **Push origin**.

No LFS commands are required.

## 11. Important rule for future large files

This package works without Git LFS because every individual file is below GitHub's ordinary-Git hard limit at the time this package was prepared. If you later add or replace a binary file, check its size first.

If a future file exceeds GitHub's normal single-object limit, do **not** attempt to push it as an ordinary Git object. Either reduce/split the asset, host that separate asset elsewhere, or revisit your storage strategy.

## 12. Optional repository integrity check

The repository includes `scripts/verify_repo.py`. This is not required for publishing with GitHub Desktop. If you are comfortable running Python locally, you can optionally verify the original submission hashes with:

```text
python scripts/verify_repo.py --verify-originals
```

The check confirms required files, Python syntax, and the SHA-256 values of the preserved originals.

---

## Official GitHub references

- GitHub Desktop — adding a local repository: https://docs.github.com/en/desktop/adding-and-cloning-repositories/adding-a-repository-from-your-local-computer-to-github-desktop
- GitHub Desktop — publishing an existing project: https://docs.github.com/en/desktop/adding-and-cloning-repositories/adding-an-existing-project-to-github-using-github-desktop
- GitHub — large-file limits: https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github

---

**Recommended publication path:** extract ZIP → GitHub Desktop → Add Local Repository → review Changes → Commit to `main` → Publish repository → verify on GitHub.
