import dash
from dash import dcc, html, Input, Output
import json
import networkx as nx
import pandas as pd
from pyvis.network import Network
import plotly.express as px
from flask import Flask
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import base64
import io

# Load Citation Data (from graph.json)
def load_graph():
    with open("graph.json", "r") as f:
        return json.load(f)

graph_data = load_graph()

# Create Citation Graph
def create_network(graph_data):
    G = nx.DiGraph()
    for node in graph_data["nodes"]:
        G.add_node(node["id"], label=node["label"], year=node.get("year", "Unknown"))
    for link in graph_data["links"]:
        G.add_edge(link["source"], link["target"])
    return G

G = create_network(graph_data)

# Function to generate citation network using Pyvis
def create_pyvis_graph(G):
    net = Network(height="500px", width="100%", directed=True)
    net.from_nx(G)
    net.save_graph("network.html")

# Function to generate word cloud from paper titles
def generate_wordcloud(graph_data):
    text = " ".join(node["label"] for node in graph_data["nodes"])
    wordcloud = WordCloud(width=800, height=400, background_color="white").generate(text)
    img = io.BytesIO()
    plt.figure(figsize=(8, 4))
    plt.imshow(wordcloud, interpolation="bilinear")
    plt.axis("off")
    plt.savefig(img, format='png')
    plt.close()
    img.seek(0)
    return base64.b64encode(img.getvalue()).decode()

# Flask Server
server = Flask(__name__)

# Initialize Dash App
app = dash.Dash(__name__, server=server)

# App Layout
app.layout = html.Div([
    html.H1("Citation Network Visualization", style={"text-align": "center"}),

    dcc.Upload(id="upload-data", children=html.Button("Upload graph.json"), multiple=False),

    dcc.Tabs([
        dcc.Tab(label="Citation Network", children=[
            html.Iframe(src="network.html", height="500px", width="100%")
        ]),
        
        dcc.Tab(label="Top Cited Papers", children=[
            dcc.Graph(id="top-cited")
        ]),

        dcc.Tab(label="Word Cloud", children=[
            html.Img(id="wordcloud", style={"width": "100%"})
        ])
    ])
])

# Callbacks for interactive features
@app.callback(
    Output("top-cited", "figure"),
    Output("wordcloud", "src"),
    Input("upload-data", "contents")
)
def update_outputs(contents):
    global graph_data, G

    if contents:
        content_type, content_string = contents.split(",")
        decoded = base64.b64decode(content_string)
        graph_data = json.loads(decoded.decode("utf-8"))
    else:
        graph_data = load_graph()

    G = create_network(graph_data)
    create_pyvis_graph(G)

    # Generate Top Cited Papers Bar Chart
    top_cited = pd.DataFrame(graph_data["nodes"]).sort_values(by="cited_by", ascending=False)
    fig = px.bar(top_cited, x="label", y="cited_by", title="Top Cited Papers")

    # Generate Word Cloud
    wc = generate_wordcloud(graph_data)

    return fig, "data:image/png;base64," + wc

# Run the App
if __name__ == "__main__":
    app.run_server(debug=True)
