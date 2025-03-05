import re
import sys
import json
import time
import random
import argparse
import networkx as nx
from pathlib import Path
from urllib.parse import quote_plus, urlparse, parse_qs
from networkx.algorithms.community.modularity_max import greedy_modularity_communities
from requests_html import HTMLSession

# Initialize session
session = HTMLSession()
seen = set()

def main():
    parser = argparse.ArgumentParser(description="Google Scholar Citation Scraper & Network Visualizer")
    parser.add_argument("query", help="Article title or Google Scholar search URL")
    parser.add_argument("--depth", type=int, default=1, help="Depth of the crawl")
    parser.add_argument("--pages", type=int, default=1, help="Number of pages to scrape")
    parser.add_argument("--output", type=str, default="output", help="Output file prefix")
    parser.add_argument("--debug", action="store_true", default=False, help="Enable debugging")

    args = parser.parse_args()

    # Check if input is a title (convert to Google Scholar search URL)
    if not args.query.startswith("http"):
        search_query = quote_plus(args.query)
        args.query = f"https://scholar.google.com/scholar?q={search_query}"
        print(f"Generated Google Scholar URL: {args.query}")

    # Create directed graph
    g = nx.DiGraph()

    # Crawl and build the graph
    for from_pub, to_pub in get_citations(args.query, depth=args.depth, pages=args.pages):
        g.add_node(from_pub['id'], label=from_pub['title'], **remove_nones(from_pub))
        if to_pub:
            g.add_node(to_pub['id'], label=to_pub['title'], **remove_nones(to_pub))
            g.add_edge(from_pub['id'], to_pub['id'])

    # Cluster the nodes using modularity maximization
    cluster_nodes(g)

    # Save outputs
    write_output(g, args)

def get_citations(url, depth=1, pages=1):
    """ Recursively fetch citations from Google Scholar """
    if url in seen:
        return
    seen.add(url)

    html = get_html(url)

    # Get the parent publication (if exists)
    a = html.find('#gs_res_ccl_top a', first=True)
    to_pub = {"id": get_cluster_id(url), "title": a.text} if a else None

    for e in html.find('#gs_res_ccl_mid .gs_r'):
        from_pub = get_metadata(e, to_pub)
        if from_pub:
            yield from_pub, to_pub

            # Recursive depth-first search
            if depth > 0 and from_pub['cited_by_url']:
                yield from get_citations(from_pub['cited_by_url'], depth=depth-1, pages=pages)

    # Handle pagination
    if pages > 1:
        next_link = html.find('#gs_n a:contains("Next")', first=True)
        if next_link:
            yield from get_citations(f"https://scholar.google.com{next_link.attrs['href']}", depth=depth, pages=pages-1)

def get_html(url):
    """ Fetch page content using requests_html """
    time.sleep(random.randint(1, 5))  # Random delay to avoid Google rate limits
    response = session.get(url)

    # Print part of the HTML response for debugging
    if "captcha" in response.html.html.lower():
        sys.exit("Google Scholar is blocking the request with a CAPTCHA. Solve it manually before proceeding.")

    return response.html

def get_metadata(e, to_pub):
    """ Extract publication metadata """
    article_id = get_id(e)
    if not article_id:
        return None

    a = e.find('.gs_rt a', first=True)
    title, url = (a.text, a.attrs['href']) if a else ("Unknown Title", None)

    meta = e.find('.gs_a', first=True).text
    authors, source, year = parse_meta(meta)

    cited_by, cited_by_url = None, None
    for a in e.find('.gs_fl a'):
        if 'Cited by' in a.text:
            cited_by = int(re.search(r'Cited by (\d+)', a.text).group(1))
            cited_by_url = f"https://scholar.google.com{a.attrs['href']}"

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
    meta_parts = re.split(r'\W-\W', meta)
    authors, source = meta_parts[:2] if len(meta_parts) >= 2 else (meta_parts[0], None)
    year = source.split(',')[-1].strip() if source and ',' in source else source
    return authors, source, year

def get_id(e):
    """ Extract Google Scholar cluster ID """
    for a in e.find('.gs_fl a'):
        if 'Cited by' in a.text or 'versions' in a.text:
            return get_cluster_id(a.attrs['href'])
    return e.attrs.get('data-cid')

def get_cluster_id(url):
    """ Extracts the unique cluster ID from a URL """
    for param in ['cluster', 'cites']:
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
            g.nodes[node]['modularity'] = i

def write_output(g, args):
    """ Save graph in multiple formats """
    if len(g.nodes) == 0:
        print("No nodes found. Skipping output.")
        return  # Prevent writing an empty JSON

    nx.write_gexf(g, f"{args.output}.gexf")
    nx.write_graphml(g, f"{args.output}.graphml")

    # Save JSON for visualization
    graph_json = to_json(g)
    json_output_path = Path("graph.json")
    json_output_path.write_text(json.dumps(graph_json, indent=4))
    print(f"Graph JSON saved to {json_output_path}")

def to_json(g):
    """ Convert graph to JSON format """
    return {
        "nodes": [{"id": n, **d} for n, d in g.nodes(data=True)],
        "links": [{"source": u, "target": v} for u, v in g.edges()]
    }

if __name__ == "__main__":
    main()
