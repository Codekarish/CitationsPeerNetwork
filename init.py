#!/usr/bin/env python

import re
import sys
import json
import time
import random
import argparse
import networkx as nx
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from urllib.parse import urlparse, parse_qs
from networkx.algorithms.community.modularity_max import greedy_modularity_communities

# Global Variables
seen = set()
driver = None

def main():
    global driver

    parser = argparse.ArgumentParser(description="Google Scholar Citation Scraper & Network Visualizer")
    parser.add_argument("url", help="Starting Google Scholar search URL")
    parser.add_argument("--depth", type=int, default=1, help="Depth of crawl in terms of citation levels")
    parser.add_argument("--pages", type=int, default=1, help="Number of pages to scrape per level")
    parser.add_argument("--output", type=str, default="graph", help="Output file prefix")
    parser.add_argument("--debug", action="store_true", default=False, help="Enable debug logging")

    args = parser.parse_args()

    # Set up Selenium WebDriver
    driver = webdriver.Chrome()

    # Create a directed graph for citations
    g = nx.DiGraph()

    # Crawl and collect citation data
    for from_pub, to_pub in get_citations(args.url, depth=args.depth, pages=args.pages):
        g.add_node(from_pub['id'], label=from_pub['title'], **remove_nones(from_pub))
        if to_pub:
            g.add_node(to_pub['id'], label=to_pub['title'], **remove_nones(to_pub))
            g.add_edge(from_pub['id'], to_pub['id'])

    # Cluster nodes for modularity detection
    cluster_nodes(g)

    # Save outputs
    write_output(g, args)

    # Close Selenium WebDriver
    driver.quit()

def get_citations(url, depth=1, pages=1):
    """ Recursively fetch citations from Google Scholar """
    if url in seen:
        return
    seen.add(url)

    html = get_html(url)

    # Get the parent publication (if exists)
    a = html.find_element(By.CSS_SELECTOR, "#gs_res_ccl_top a")
    to_pub = {"id": get_cluster_id(url), "title": a.text} if a else None

    for e in html.find_elements(By.CSS_SELECTOR, "#gs_res_ccl_mid .gs_r"):
        from_pub = get_metadata(e, to_pub)
        if from_pub:
            yield from_pub, to_pub

            # Recursive depth-first search for deeper citations
            if depth > 0 and from_pub['cited_by_url']:
                yield from get_citations(from_pub['cited_by_url'], depth=depth - 1, pages=pages)

    # Handle pagination
    if pages > 1:
        try:
            next_link = html.find_element(By.CSS_SELECTOR, "#gs_n a")
            if next_link.text == "Next":
                next_url = "https://scholar.google.com" + next_link.get_attribute("href")
                yield from get_citations(next_url, depth=depth, pages=pages - 1)
        except NoSuchElementException:
            pass  # No next page found

def get_html(url):
    """ Uses Selenium WebDriver to fetch the Scholar page """
    global driver

    time.sleep(random.randint(1, 5))  # Random delay to reduce blocking
    driver.get(url)

    while True:
        try:
            # Check if a CAPTCHA is present
            driver.find_element(By.CSS_SELECTOR, "#gs_captcha_ccl,#recaptcha")
            print("CAPTCHA detected! Solve it manually in the browser.")
            time.sleep(10)
        except NoSuchElementException:
            return driver  # Return the loaded page

def get_metadata(e, to_pub):
    """ Extract publication metadata """
    article_id = get_id(e)
    if not article_id:
        return None

    # Extract Title & URL
    try:
        a = e.find_element(By.CSS_SELECTOR, ".gs_rt a")
        title, url = a.text, a.get_attribute("href")
    except NoSuchElementException:
        title, url = None, None

    # Extract Author & Year Metadata
    meta = e.find_element(By.CSS_SELECTOR, ".gs_a").text
    authors, source, year = parse_meta(meta)

    # Extract Citation Data
    cited_by, cited_by_url = None, None
    for a in e.find_elements(By.CSS_SELECTOR, ".gs_fl a"):
        if "Cited by" in a.text:
            cited_by = int(re.search(r"Cited by (\d+)", a.text).group(1))
            cited_by_url = "https://scholar.google.com" + a.get_attribute("href")

    return {
        "id": article_id,
        "url": url,
        "title": title,
        "authors": authors,
        "year": year,
        "cited_by": cited_by,
        "cited_by_url": cited_by_url,
    }

def parse_meta(meta):
    """ Extract author and publication year from metadata """
    meta_parts = re.split(r"\W-\W", meta)
    authors, source = meta_parts[:2] if len(meta_parts) >= 2 else (meta_parts[0], None)
    year = source.split(",")[-1].strip() if source and "," in source else source
    return authors, source, year

def get_id(e):
    """ Extract the Google Scholar cluster ID """
    for a in e.find_elements(By.CSS_SELECTOR, ".gs_fl a"):
        if "Cited by" in a.text or "versions" in a.text:
            return get_cluster_id(a.get_attribute("href"))
    return e.get_attribute("data-cid")

def get_cluster_id(url):
    """ Extracts the unique cluster ID from a URL """
    for param in ["cluster", "cites"]:
        vals = parse_qs(urlparse(url).query).get(param, [])
        if vals:
            return vals[0]
    return None

def remove_nones(d):
    """ Remove None values from a dictionary """
    return {k: v for k, v in d.items() if v is not None}

def cluster_nodes(g):
    """ Apply modularity maximization clustering """
    undirected_g = nx.Graph(g)
    for i, comm in enumerate(greedy_modularity_communities(undirected_g)):
        for node in comm:
            g.nodes[node]["modularity"] = i

def write_output(g, args):
    """ Save graph in multiple formats """
    nx.write_gexf(g, f"{args.output}.gexf")
    nx.write_graphml(g, f"{args.output}.graphml")

    # Save JSON for visualization
    graph_json = to_json(g)
    json_output_path = Path("graph.json")
    json_output_path.write_text(json.dumps(graph_json, indent=4))

    print(f"Graph JSON saved at: {json_output_path}")

def to_json(g):
    """ Convert graph to JSON format """
    return {
        "nodes": [{"id": n, **d} for n, d in g.nodes(data=True)],
        "links": [{"source": u, "target": v} for u, v in g.edges()]
    }

if __name__ == "__main__":
    main()
