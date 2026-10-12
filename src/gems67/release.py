"""Fail-closed release decision. No unknown, NaN, absent or stale gate is approval."""
import hashlib
import math

def release_decision(card):
    reasons=[]
    gates=('holdout_gain','tip_gain','current_best_beaten','feature_canaries','surface_registry','dots_registry','all_prior_hash_pixel_checks','format_valid')
    for gate in gates:
        if card.get('gates',{}).get(gate) is not True:reasons.append(gate+' missing or failed')
    if card.get('registry_complete') is not True:reasons.append('registry inventory incomplete')
    d=card.get('paired_dti_ci95')
    if not isinstance(d,list) or len(d)!=2 or any(type(x) not in (float,int) or not math.isfinite(x) for x in d) or not(0<d[0]<=d[1]):reasons.append('positive paired confidence interval absent')
    sha=card.get('raster_sha256')
    if not isinstance(sha,str) or len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha):reasons.append('raster hash absent or invalid')
    return {'verdict':'negative' if reasons else 'promote','download_enabled':not reasons,'reasons':reasons,'weekly_slot_approved':False}

def verified_download(card,path):
    result=release_decision(card)
    if not result['download_enabled']:raise ValueError('; '.join(result['reasons']))
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    if h.hexdigest()!=card['raster_sha256']:raise ValueError('stale or changed artifact')
    return result
