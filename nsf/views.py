# Create your views here.
from lib.database import generalize
from lib.sdb_database import Author, Institution
from utils import json_response

def to_val_list(named_tpls, name_lookup_fn, doc_lookup_fn = lambda t: t.doc_count):
    return [{'label': '%s : %d' % (name_lookup_fn(named_tpl), doc_lookup_fn(named_tpl)),
             'value': name_lookup_fn(named_tpl)}
            for named_tpl in named_tpls]

@json_response
def top_authors(request):
    if request.method == 'GET':
        term = request.GET.get('term')
        n = request.GET.get('n', 10)
        entities_and_counts = Author.name_like_top(generalize(term), n=n)
        val_list = to_val_list(entities_and_counts, name_lookup_fn=lambda t: t.Author.name)
        return val_list

@json_response
def top_institutions(request):
    if request.method == 'GET':
        term = request.GET.get('term')
        n = request.GET.get('n', 10)
        entities_and_counts = Institution.name_like_top(generalize(term), n=n)
        val_list = to_val_list(entities_and_counts, name_lookup_fn=lambda t: t.Institution.name)
        return val_list
