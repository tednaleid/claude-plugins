#!/usr/bin/env node

import { readFileSync, writeFileSync, readdirSync, statSync } from 'fs';
import { resolve, dirname, join } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(__dirname, '..');

// A script line tagged with this marker gets the plugin's version stamped into
// its first quoted string, so a standalone-installed copy can report a version
// that tracks plugin.json without reading it at runtime.
const VERSION_MARKER = 'SYNC_PLUGIN_VERSION';

function walkFiles(dir: string): string[] {
  let entries: string[];
  try {
    entries = readdirSync(dir);
  } catch {
    return [];
  }
  const files: string[] = [];
  for (const entry of entries) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) files.push(...walkFiles(path));
    else files.push(path);
  }
  return files;
}

function stampPluginVersion(pluginName: string, pluginPath: string, version: string) {
  for (const file of walkFiles(join(pluginPath, 'scripts'))) {
    let text: string;
    try {
      text = readFileSync(file, 'utf-8');
    } catch {
      continue;
    }
    if (!text.includes(VERSION_MARKER)) continue;
    const updated = text
      .split('\n')
      .map((line) =>
        line.includes(VERSION_MARKER)
          ? line.replace(/(["'])[^"']*\1/, (_m, q) => `${q}${version}${q}`)
          : line,
      )
      .join('\n');
    if (updated !== text) {
      writeFileSync(file, updated);
      console.log(`Stamped ${pluginName} v${version} into ${file}`);
    }
  }
}

function discoverPlugins() {
  const pluginsDir = resolve(projectRoot, 'plugins');
  const plugins = [];

  try {
    const entries = readdirSync(pluginsDir);

    for (const entry of entries) {
      const pluginPath = join(pluginsDir, entry);
      const pluginJsonPath = join(pluginPath, '.claude-plugin/plugin.json');

      if (!statSync(pluginPath).isDirectory()) continue;

      try {
        const pluginJson = JSON.parse(readFileSync(pluginJsonPath, 'utf-8'));

        const plugin: any = {
          name: pluginJson.name,
          source: `./plugins/${entry}`,
          description: pluginJson.description,
          version: pluginJson.version,
          author: pluginJson.author,
        };

        if (pluginJson.homepage) plugin.homepage = pluginJson.homepage;
        if (pluginJson.repository) plugin.repository = pluginJson.repository;
        if (pluginJson.license) plugin.license = pluginJson.license;
        if (pluginJson.keywords) plugin.keywords = pluginJson.keywords;
        if (pluginJson.category) plugin.category = pluginJson.category;

        plugins.push(plugin);
        stampPluginVersion(pluginJson.name, pluginPath, pluginJson.version);
        console.log(`Discovered plugin: ${pluginJson.name}`);
      } catch (err) {
        console.warn(`Skipping ${entry}: no valid plugin.json`);
      }
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error(`Failed to read plugins directory:`, message);
  }

  return plugins;
}

function syncMarketplace() {
  const marketplacePath = resolve(
    projectRoot,
    '.claude-plugin/marketplace.json',
  );
  const marketplace = JSON.parse(readFileSync(marketplacePath, 'utf-8'));

  marketplace.plugins = discoverPlugins();

  writeFileSync(marketplacePath, JSON.stringify(marketplace, null, 2) + '\n');
  console.log(
    `Marketplace synced successfully with ${marketplace.plugins.length} plugins`,
  );
}

syncMarketplace();
