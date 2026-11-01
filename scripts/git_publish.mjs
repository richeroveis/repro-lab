// Publish branches to GitHub using the GITHUB_TOKEN that lives in this project's
// own .env. The token is never printed: it is handed to git through GIT_ASKPASS,
// and git is told not to use any credential helper or interactive prompt.
//
// usage:
//   node scripts/git_publish.mjs main        # push the current branch
//   node scripts/git_publish.mjs gh-pages    # push frontend/dist as gh-pages
//   node scripts/git_publish.mjs both

import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const REPO = 'https://x-access-token@github.com/richeroveis/repro-lab.git';
const ASKPASS = path.join(process.cwd(), '.git-askpass.cmd');
const GH_PAGES_WORKTREE = path.join(process.cwd(), '.gh-pages-work');

function token() {
  const line = fs
    .readFileSync('.env', 'utf8')
    .split(/\r?\n/)
    .find((l) => l.startsWith('GITHUB_TOKEN='));
  if (!line) throw new Error('GITHUB_TOKEN missing from .env');
  return line.slice('GITHUB_TOKEN='.length).trim().replace(/^["']|["']$/g, '');
}

function git(args) {
  const t = token();
  // The URL already carries the username, so git only asks for the password.
  // Nothing is echoed to the console: the value goes to git's stdin only.
  fs.writeFileSync(ASKPASS, '@echo off\r\necho %REPROLAB_TOKEN%\r\n', 'utf8');
  try {
    return execFileSync('git', ['-c', 'credential.helper=', ...args], {
      encoding: 'utf8',
      env: { ...process.env, GIT_TERMINAL_PROMPT: '0', GIT_ASKPASS: ASKPASS, REPROLAB_TOKEN: t },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
  } catch (err) {
    const out = [err.stdout, err.stderr].filter(Boolean).join('\n');
    const scrubbed = out.split(t).join('[token redacted]');
    throw new Error('git failed: ' + scrubbed.slice(0, 600));
  } finally {
    fs.rmSync(ASKPASS, { force: true });
  }
}

function pushBranch() {
  const branch = execFileSync('git', ['rev-parse', '--abbrev-ref', 'HEAD'], { encoding: 'utf8' }).trim();
  const out = git(['push', '--force', REPO, `HEAD:refs/heads/${branch}`]);
  console.log('pushed', branch, out.split('\n').filter((l) => l.includes(branch) || l.includes('new') || l.includes('force')).join(' | ').slice(0, 200));
}

function pushGhPages() {
  const dist = path.join(process.cwd(), 'frontend', 'dist');
  if (!fs.existsSync(path.join(dist, 'index.html'))) throw new Error('build frontend/dist first');
  fs.rmSync(GH_PAGES_WORKTREE, { recursive: true, force: true });
  fs.mkdirSync(GH_PAGES_WORKTREE, { recursive: true });
  try {
    // A standalone repo inside the project keeps the Pages branch free of the
    // source history: the published tree is exactly the built notebook.
    execFileSync('git', ['-C', GH_PAGES_WORKTREE, 'init', '-q', '-b', 'gh-pages'], { stdio: 'pipe' });
    for (const entry of fs.readdirSync(dist)) {
      fs.cpSync(path.join(dist, entry), path.join(GH_PAGES_WORKTREE, entry), { recursive: true, force: true });
    }
    execFileSync('git', ['-C', GH_PAGES_WORKTREE, 'add', '-A'], { stdio: 'pipe' });
    execFileSync('git', ['-C', GH_PAGES_WORKTREE, '-c', 'user.name=tidex22', '-c', 'user.email=tidex22@users.noreply.github.com', 'commit', '-q', '-m', 'ReproLab notebook build for GitHub Pages'], { stdio: 'pipe' });
    const out = git(['-C', GH_PAGES_WORKTREE, 'push', '--force', REPO, 'HEAD:refs/heads/gh-pages']);
    console.log('pushed gh-pages', String(out).slice(-200));
  } finally {
    fs.rmSync(GH_PAGES_WORKTREE, { recursive: true, force: true });
  }
}

const what = process.argv[2] || 'both';
if (what === 'main' || what === 'both') pushBranch();
if (what === 'gh-pages' || what === 'both') pushGhPages();
