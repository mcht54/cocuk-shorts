"""Blender içinde çalışır: blender -b --factory-startup -P blender_sahne.py -- <komut> ...

Komutlar:
  kur    <plan.json> <is_dizini> [ornekleme] [olcek_yuzde]
         Mekânı, rig'li karakterleri, nesneleri, kamerayı ve ışığı kurar; plandaki her kareyi
         anahtar kare olarak yazar; sahne.blend kaydeder; meta.json (kare kare ölçüm) üretir.
  render <is_dizini> <bas_kare> <son_kare>
         sahne.blend'den aralığı render eder; var olan kareleri atlar (kaldığı yerden devam).
Karakterler koddan üretilir; aynı tanım her bölümde birebir aynı modeli verir.
"""
import hashlib
import json
import math
import os
import random
import sys
from pathlib import Path

import bmesh
import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector

KEMIKLER = {
    # ad: (baş, kuyruk, ebeveyn) — boy=1 için, ön yüz –Y
    "kok": ((0, 0, 0), (0, 0, 0.12), None),
    "govde": ((0, 0, 0.25), (0, 0, 0.62), "kok"),
    "bas": ((0, 0, 0.62), (0, 0, 1.0), "govde"),
    "agiz": ((0, -0.232, 0.715), (0, -0.29, 0.715), "bas"),
    "goz.L": ((0.085, -0.175, 0.84), (0.085, -0.25, 0.84), "bas"),
    "goz.R": ((-0.085, -0.175, 0.84), (-0.085, -0.25, 0.84), "bas"),
    "kas.L": ((0.085, -0.19, 0.93), (0.085, -0.26, 0.93), "bas"),
    "kas.R": ((-0.085, -0.19, 0.93), (-0.085, -0.26, 0.93), "bas"),
    "kol.L": ((0.2, -0.02, 0.58), (0.23, -0.02, 0.33), "govde"),
    "kol.R": ((-0.2, -0.02, 0.58), (-0.23, -0.02, 0.33), "govde"),
    "bacak.L": ((0.1, 0, 0.3), (0.1, 0, 0.03), "kok"),
    "bacak.R": ((-0.1, 0, 0.3), (-0.1, 0, 0.03), "kok"),
    "kuyruk": ((0, 0.17, 0.33), (0, 0.3, 0.45), "govde"),
    "kulak.L": ((0.1, 0, 0.95), (0.12, 0, 1.2), "bas"),
    "kulak.R": ((-0.1, 0, 0.95), (-0.12, 0, 1.2), "bas"),
}


# ------------------------------------------------------------------ yardımcılar
def malzeme(ad, renk, puruz=0.55, isima=0.0, ic_sacilma=0.0):
    m = bpy.data.materials.get(ad)
    if m:
        return m
    m = bpy.data.materials.new(ad)
    m.use_nodes = True
    p = m.node_tree.nodes.get("Principled BSDF")
    p.inputs["Base Color"].default_value = (*renk, 1)
    p.inputs["Roughness"].default_value = puruz
    if ic_sacilma:
        p.inputs["Subsurface Weight"].default_value = ic_sacilma
        p.inputs["Subsurface Radius"].default_value = (0.1, 0.05, 0.03)
    if isima:
        p.inputs["Emission Color"].default_value = (*renk, 1)
        p.inputs["Emission Strength"].default_value = isima
    m.diffuse_color = (*renk, 1)
    return m


def _nesne(ad, bm, mat, koleksiyon, yumusak=True):
    me = bpy.data.meshes.new(ad)
    bm.to_mesh(me)
    bm.free()
    if yumusak:
        for p in me.polygons:
            p.use_smooth = True
    me.materials.append(mat)
    ob = bpy.data.objects.new(ad, me)
    koleksiyon.objects.link(ob)
    return ob


def kure(ad, r, konum, olcek, mat, kol, seg=32, ico=False):
    bm = bmesh.new()
    if ico:
        bmesh.ops.create_icosphere(bm, subdivisions=2, radius=r)
    else:
        bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=seg // 2, radius=r)
    ob = _nesne(ad, bm, mat, kol)
    ob.location = konum
    ob.scale = olcek
    return ob


def silindir(ad, r1, r2, yuk, konum, mat, kol, seg=20, yumusak=True):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg, radius1=r1, radius2=r2, depth=yuk)
    ob = _nesne(ad, bm, mat, kol, yumusak)
    ob.location = (konum[0], konum[1], konum[2] + yuk / 2)
    return ob


def kemige_bagla(ob, arm, kemik):
    bpy.context.view_layer.update()  # matrix_world ancak güncellemeden sonra doğru (ilk parça hatası)
    mw = ob.matrix_world.copy()
    ob.parent = arm
    ob.parent_type = "BONE"
    ob.parent_bone = kemik
    bpy.context.view_layer.update()
    ob.matrix_world = mw


# ------------------------------------------------------------------ karakter
def karakter_kur(tanim):
    k = tanim["id"]
    boy = tanim.get("boy", 1.0)
    renk = tanim["renk"]
    kol = bpy.data.collections.new(f"karakter_{k}")
    bpy.context.scene.collection.children.link(kol)

    ad = bpy.data.armatures.new(f"{k}_iskelet")
    arm = bpy.data.objects.new(f"{k}", ad)
    kol.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    for b, (h, t, ebeveyn) in KEMIKLER.items():
        eb = ad.edit_bones.new(b)
        eb.head = Vector(h) * boy
        eb.tail = Vector(t) * boy
        if ebeveyn:
            eb.parent = ad.edit_bones[ebeveyn]
    bpy.ops.object.mode_set(mode="OBJECT")
    for pb in arm.pose.bones:
        pb.rotation_mode = "XYZ"
    ad.display_type = "STICK"
    arm.hide_render = True  # iskelet görünmez; yalnız gövdeyi taşır

    M = {n: malzeme(f"{k}_{n}", c, 0.6, ic_sacilma=0.15 if n in ("kurk", "karin") else 0.0)
         for n, c in renk.items()}
    M["beyaz"] = malzeme("goz_beyaz", (0.97, 0.97, 0.97), 0.25)
    M["agiz"] = malzeme("agiz_ic", (0.40, 0.06, 0.09), 0.5)
    M["parlama"] = malzeme("goz_parlama", (1, 1, 1), 0.1, isima=4.0)
    M.setdefault("kulak_ici", M["karin"])

    def p(x, y, z):
        return (x * boy, y * boy, z * boy)

    def s(*v):
        return tuple(a * boy for a in v)

    parcalar = [
        ("govde", kure("govde", 0.2, p(0, 0, 0.42), s(1, 0.9, 1.15), M["kurk"], kol)),
        ("govde", kure("karin", 0.15, p(0, -0.075, 0.40), s(0.95, 0.6, 1.1), M["karin"], kol)),
        ("bas", kure("bas", 0.22, p(0, -0.01, 0.79), s(1.05, 0.95, 0.95), M["kurk"], kol)),
        ("bas", kure("burunluk", 0.1, p(0, -0.17, 0.735), s(1.2, 0.7, 0.8), M["karin"], kol)),
        ("bas", kure("burun", 0.032, p(0, -0.243, 0.77), s(1.1, 0.9, 0.8), M["burun"], kol)),
        ("agiz", kure("agiz", 0.03, p(0, -0.232, 0.712), s(1.35, 0.55, 0.42), M["agiz"], kol)),
    ]
    for t, x in (("L", 1), ("R", -1)):
        parcalar += [
            (f"goz.{t}", kure(f"goz_{t}", 0.055, p(0.085 * x, -0.175, 0.84), s(1, 0.7, 1.15), M["beyaz"], kol)),
            (f"goz.{t}", kure(f"gozbebek_{t}", 0.034, p(0.088 * x, -0.214, 0.835), s(1, 0.7, 1.15), M["goz"], kol)),
            (f"goz.{t}", kure(f"parlama_{t}", 0.011, p(0.1 * x, -0.243, 0.857), s(1, 1, 1), M["parlama"], kol, seg=12)),
            (f"kas.{t}", kure(f"kas_{t}", 0.03, p(0.085 * x, -0.19, 0.93), s(1.7, 0.55, 0.42), M["burun"], kol)),
            ("bas", kure(f"yanak_{t}", 0.04, p(0.14 * x, -0.165, 0.735), s(1, 0.4, 0.7), M["yanak"], kol)),
            (f"kol.{t}", kure(f"kol_{t}", 0.055, p(0.215 * x, -0.02, 0.46), s(1, 1, 2.3), M["kurk"], kol)),
            (f"kol.{t}", kure(f"el_{t}", 0.056, p(0.23 * x, -0.02, 0.33), s(1, 1, 1), M["karin"], kol)),
            (f"bacak.{t}", kure(f"bacak_{t}", 0.07, p(0.1 * x, 0, 0.17), s(1, 1, 1.6), M["kurk"], kol)),
            (f"bacak.{t}", kure(f"ayak_{t}", 0.075, p(0.1 * x, -0.045, 0.04), s(1, 1.5, 0.55), M["karin"], kol)),
        ]
        if tanim["tur"] == "tavsan":
            parcalar += [
                (f"kulak.{t}", kure(f"kulak_{t}", 0.06, p(0.105 * x, 0, 1.1), s(0.8, 0.45, 2.6), M["kurk"], kol)),
                (f"kulak.{t}", kure(f"kulak_ici_{t}", 0.045, p(0.105 * x, -0.024, 1.1), s(0.6, 0.3, 2.3),
                                    M["kulak_ici"], kol)),
            ]
        else:
            kulak = silindir(f"kulak_{t}", 0.055 * boy, 0.0, 0.12 * boy, p(0.12 * x, 0, 0.94), M["kurk"], kol)
            parcalar.append((f"kulak.{t}", kulak))
    if tanim["tur"] == "tavsan":
        parcalar.append(("kuyruk", kure("kuyruk", 0.075, p(0, 0.2, 0.3), s(1, 1, 1), M["karin"], kol)))
    else:  # sincap: üç boğumlu kabarık kuyruk
        for i, (y, z, r) in enumerate(((0.24, 0.33, 0.11), (0.34, 0.55, 0.13), (0.31, 0.79, 0.12))):
            parcalar.append(("kuyruk", kure(f"kuyruk_{i}", r, p(0, y, z), s(0.85, 0.9, 1.2),
                                            M["kurk"] if i < 2 else M["karin"], kol)))
    for kemik, ob in parcalar:
        # ad sahnedeki diğer karakterlerden bağımsız olsun (Blender'ın .001 ekleri parmak izini bozuyordu)
        ob.name = f"{k}_{ob.name.split('.')[0]}"
        kemige_bagla(ob, arm, kemik)
    return arm, kol


def parmak_izi(kol):
    """Karakter modelinin değişmez özeti: tutarlılık testi için."""
    h = hashlib.sha1()
    for ob in sorted(kol.objects, key=lambda o: o.name):
        if ob.type != "MESH":
            continue
        h.update(ob.name.encode())
        h.update(str(len(ob.data.vertices)).encode())
        h.update(("%.4f %.4f %.4f" % tuple(ob.dimensions)).encode())
        for m in ob.data.materials:
            h.update(("%.3f %.3f %.3f" % tuple(m.diffuse_color[:3])).encode())
    return h.hexdigest()[:16]


# ------------------------------------------------------------------ nesneler
def palamut_kur(ad, konum, kol):
    bos = bpy.data.objects.new(ad, None)
    kol.objects.link(bos)
    bos.location = (konum[0], konum[1], konum[2] + 0.08)
    govde = kure(f"{ad}_govde", 0.07, (0, 0, 0), (1, 1, 1.15), malzeme("palamut", (0.62, 0.36, 0.12), 0.35), kol)
    sapka = kure(f"{ad}_sapka", 0.078, (0, 0, 0.05), (1, 1, 0.55), malzeme("palamut_sapka", (0.33, 0.21, 0.09), 0.9), kol)
    sap = silindir(f"{ad}_sap", 0.012, 0.008, 0.05, (0, 0, 0.08), malzeme("palamut_sapka", (0.33, 0.21, 0.09)), kol)
    for o in (govde, sapka, sap):
        o.parent = bos
    return bos


def harita_kur(ad, konum, kol):
    """Rulo hazine haritası: krem kâğıt, kırmızı kurdele."""
    bos = bpy.data.objects.new(ad, None)
    kol.objects.link(bos)
    bos.location = (konum[0], konum[1], konum[2] + 0.05)
    rulo = silindir(f"{ad}_rulo", 0.045, 0.045, 0.26, (-0.13, 0, 0), malzeme("harita", (0.95, 0.86, 0.62), 0.8), kol)
    rulo.rotation_euler = (0, math.radians(90), 0)
    kurdele = silindir(f"{ad}_kurdele", 0.05, 0.05, 0.03, (-0.015, 0, 0), malzeme("kurdele", (0.85, 0.15, 0.2), 0.5), kol)
    kurdele.rotation_euler = (0, math.radians(90), 0)
    for o in (rulo, kurdele):
        o.parent = bos
    return bos


def top_kur(ad, konum, kol):
    bos = bpy.data.objects.new(ad, None)
    kol.objects.link(bos)
    bos.location = (konum[0], konum[1], konum[2] + 0.11)
    kure(f"{ad}_top", 0.11, (0, 0, 0), (1, 1, 1), malzeme("top", (0.15, 0.45, 0.95), 0.35), kol).parent = bos
    serit = kure(f"{ad}_serit", 0.112, (0, 0, 0), (1, 1, 0.25), malzeme("top_serit", (1.0, 0.85, 0.2), 0.35), kol)
    serit.parent = bos
    return bos


def sandik_kur(ad, konum, kol):
    """Hazine sandığı; kapak menteşe boşluğu "<ad>_kapak" ile açılır (plan: tutma[...]['_ac'])."""
    bos = bpy.data.objects.new(ad, None)
    kol.objects.link(bos)
    bos.location = (konum[0], konum[1], konum[2])
    tahta = malzeme("sandik", (0.55, 0.32, 0.14), 0.7)
    altin = malzeme("altin", (1.0, 0.75, 0.2), 0.3, isima=0.4)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2)
    govde = _nesne(f"{ad}_govde", bm, tahta, kol, yumusak=False)
    govde.scale, govde.location, govde.parent = (0.26, 0.18, 0.13), (0, 0, 0.13), bos
    for x in (-0.2, 0.2):
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2)
        b = _nesne(f"{ad}_bant", bm, altin, kol, yumusak=False)
        b.scale, b.location, b.parent = (0.025, 0.185, 0.135), (x, 0, 0.13), bos
    mentese = bpy.data.objects.new(f"{ad}_kapak", None)
    kol.objects.link(mentese)
    mentese.parent, mentese.location = bos, (0, 0.18, 0.26)
    kapak = kure(f"{ad}_kapak_ust", 0.26, (0, -0.18, 0.0), (1, 0.7, 0.35), tahta, kol)
    kapak.parent = mentese
    kure(f"{ad}_kilit", 0.035, (0, -0.19, 0.24), (1, 0.5, 1), altin, kol).parent = bos
    # içi: parlayan altınlar (kapak açılınca görünür)
    for i, (x, y) in enumerate(((-0.1, 0.0), (0.05, 0.04), (0.12, -0.03), (-0.02, -0.05))):
        kure(f"{ad}_altin{i}", 0.05, (x, y, 0.25), (1, 1, 0.5), altin, kol, seg=16).parent = bos
    return bos


def elma_kur(ad, konum, kol):
    bos = bpy.data.objects.new(ad, None)
    kol.objects.link(bos)
    bos.location = (konum[0], konum[1], konum[2] + 0.08)
    kure(f"{ad}_govde", 0.08, (0, 0, 0), (1, 1, 0.92), malzeme("elma", (0.85, 0.12, 0.12), 0.35), kol).parent = bos
    silindir(f"{ad}_sap", 0.008, 0.006, 0.05, (0, 0, 0.06), malzeme("elma_sap", (0.35, 0.22, 0.1)), kol).parent = bos
    yaprak = kure(f"{ad}_yaprak", 0.03, (0.03, 0, 0.1), (1.6, 0.6, 0.2), malzeme("elma_yaprak", (0.3, 0.65, 0.2)), kol)
    yaprak.parent = bos
    return bos


def kova_kur(ad, konum, kol):
    """Renkli oyuncak kova (sahilde kum, bahçede su taşımak için)."""
    bos = bpy.data.objects.new(ad, None)
    kol.objects.link(bos)
    bos.location = (konum[0], konum[1], konum[2])
    silindir(f"{ad}_govde", 0.08, 0.1, 0.16, (0, 0, 0), malzeme("kova", (1.0, 0.55, 0.1), 0.4), kol).parent = bos
    silindir(f"{ad}_agiz", 0.103, 0.103, 0.015, (0, 0, 0.155), malzeme("kova_agiz", (0.2, 0.6, 1.0), 0.4), kol).parent = bos
    return bos


NESNE_KUR = {"palamut": palamut_kur, "harita": harita_kur, "top": top_kur, "sandik": sandik_kur,
             "elma": elma_kur, "kova": kova_kur}


# ------------------------------------------------------------------ mekânlar
def orman_kur(tohum, kol):
    r = random.Random(tohum)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=80, y_segments=80, size=22)
    for v in bm.verts:
        d = math.hypot(v.co.x, v.co.y)
        v.co.z = 0.0 if d < 3 else 0.12 * math.sin(v.co.x * 0.7) * math.cos(v.co.y * 0.6) * min(1, (d - 3) / 3)
    _nesne("zemin", bm, malzeme("cimen", (0.30, 0.56, 0.20), 0.9), kol)
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, segments=48, radius=2.6)
    acik = _nesne("aciklik", bm, malzeme("aciklik", (0.52, 0.66, 0.30), 0.95), kol, yumusak=False)
    acik.location = (0, 0.3, 0.004)
    acik.scale = (1.3, 0.9, 1)

    govde_m = malzeme("agac_govde", (0.36, 0.22, 0.12), 0.85)
    yesiller = [malzeme(f"yaprak_{i}", c, 0.8) for i, c in
                enumerate(((0.20, 0.50, 0.16), (0.27, 0.58, 0.18), (0.16, 0.42, 0.20)))]

    def agac(x, y, olcek, buyuk=False):
        silindir("agac", 0.18 * olcek, 0.13 * olcek, 2.2 * olcek, (x, y, 0), govde_m, kol, seg=14)
        for _ in range(4 if buyuk else 3):
            kure("tac", r.uniform(0.8, 1.2) * olcek, (x + r.uniform(-0.5, 0.5) * olcek, y + r.uniform(-0.3, 0.4) * olcek,
                                                   (2.3 + r.uniform(-0.2, 0.6)) * olcek),
                 (1, 1, r.uniform(0.8, 1.0)), r.choice(yesiller), kol, ico=True)

    agac(0.4, 3.4, 1.35, buyuk=True)
    for i in range(18):
        a = r.uniform(-0.15, math.pi + 0.15)
        d = r.uniform(4.5, 11)
        agac(math.cos(a) * d * 1.3, math.sin(a) * d + 1.0, r.uniform(0.8, 1.25))
    for i in range(10):  # yanlarda ve geride çalılar
        a = r.uniform(0, math.pi)
        d = r.uniform(3.2, 6)
        kure("cali", r.uniform(0.35, 0.6), (math.cos(a) * d * 1.2, math.sin(a) * d + 0.8, 0.15),
             (1.3, 1, 0.75), r.choice(yesiller), kol, ico=True)
    tas = malzeme("tas", (0.55, 0.55, 0.58), 0.8)
    for i in range(7):
        a = r.uniform(0, math.pi)
        d = r.uniform(2.3, 4)
        kure("tas", r.uniform(0.12, 0.3), (math.cos(a) * d, math.sin(a) * d + 0.4, 0.05),
             (1.3, 1, 0.7), tas, kol, ico=True)
    kirmizi = malzeme("mantar", (0.85, 0.18, 0.15), 0.4)
    beyaz = malzeme("mantar_sap", (0.97, 0.94, 0.86), 0.6)
    for x, y in ((-2.2, 1.2), (2.4, 1.6), (-1.0, 2.4), (1.9, 0.9)):
        silindir("mantar_sap", 0.05, 0.04, 0.16, (x, y, 0), beyaz, kol)
        kure("mantar_sapka", 0.14, (x, y, 0.17), (1, 1, 0.55), kirmizi, kol)
    cicek_renk = [malzeme(f"cicek_{i}", c, 0.5) for i, c in
                  enumerate(((1, 0.55, 0.7), (1, 0.85, 0.25), (0.7, 0.5, 1), (1, 1, 1)))]
    sap = malzeme("cicek_sap", (0.22, 0.5, 0.18))
    for i in range(40):
        a = r.uniform(-0.3, math.pi + 0.3)
        d = r.uniform(1.6, 6)
        x, y = math.cos(a) * d * 1.2, math.sin(a) * d + 0.2
        if abs(x) < 2.2 and -0.8 < y < 0.9:
            continue
        silindir("sap", 0.008, 0.008, 0.18, (x, y, 0), sap, kol, seg=6, yumusak=False)
        kure("cicek", 0.045, (x, y, 0.2), (1, 1, 0.7), r.choice(cicek_renk), kol, seg=12)
    for i in range(4):  # uzak tepeler
        kure("tepe", 9, (-24 + i * 16, 30 + r.uniform(-3, 3), -5.5), (1.6, 1, 0.8),
             malzeme("tepe", (0.36, 0.58, 0.42), 0.95), kol, ico=True)


def dere_kur(tohum, kol):
    """Orman açıklığını ortadan ikiye bölen dere: üstünde basamak taşları (atlayarak geçilir)."""
    orman_kur(tohum, kol)
    su = malzeme("su", (0.25, 0.6, 0.95), 0.08, isima=0.15)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=4, y_segments=40, size=1)
    ob = _nesne("dere", bm, su, kol, yumusak=False)
    ob.scale, ob.location = (0.38, 9, 1), (0, 4, 0.012)
    kiyi = malzeme("kiyi", (0.62, 0.55, 0.42), 0.95)
    for x in (-0.42, 0.42):
        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=2, y_segments=40, size=1)
        k = _nesne("kiyi", bm, kiyi, kol, yumusak=False)
        k.scale, k.location = (0.07, 9, 1), (x, 4, 0.008)
    tas = malzeme("dere_tasi", (0.6, 0.6, 0.64), 0.7)
    # basamak taşı derenin tam ortasında (x=0): Shorts'ta yatay sıkıştırma x'i ölçekler, 0 sabit kalır
    kure("dere_tasi", 0.2, (0, 0.15, 0.0), (1.3, 1.1, 0.3), tas, kol, ico=True)
    for x, y in ((0.1, 1.3), (-0.08, 2.2), (0.06, 3.4)):
        kure("dere_tasi", 0.15, (x, y, 0.0), (1.2, 1, 0.35), tas, kol, ico=True)


def magara_kur(tohum, kol):
    """Mağara içi: koyu taş kubbe, parlayan kristaller ve mantarlar (gizem/macera mekânı)."""
    r = random.Random(tohum)
    taban = malzeme("magara_taban", (0.22, 0.18, 0.2), 0.9)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=40, y_segments=40, size=14)
    for v in bm.verts:
        v.co.z = 0.04 * math.sin(v.co.x * 2.1) * math.cos(v.co.y * 1.7)
    _nesne("zemin", bm, taban, kol)
    kaya = malzeme("kaya", (0.2, 0.15, 0.22), 0.9)
    for i in range(16):  # duvarı oluşturan iri kayalar (önde açık bırak)
        a = r.uniform(0.05, math.pi - 0.05)
        d = r.uniform(3.2, 4.2)
        kure("kaya", r.uniform(1.2, 1.9), (math.cos(a) * d * 1.4, math.sin(a) * d + 0.8, r.uniform(0.2, 1.0)),
             (1, 1, r.uniform(1.1, 1.6)), kaya, kol, ico=True)
    kure("tavan", 7, (0, 1.5, 6.2), (1.4, 1, 0.35), kaya, kol, ico=True)
    renkler = [malzeme(f"kristal_{i}", c, 0.2, isima=1.6) for i, c in
               enumerate(((0.35, 0.65, 1.0), (0.75, 0.45, 1.0), (0.3, 1.0, 0.8)))]
    # kristal kümeleri kayaların ÖNÜNDE (karakter alanı |x|<1.6, y<0.8 boş kalır)
    kumeler = [(-2.3, 1.2), (-1.4, 2.0), (0.2, 2.4), (1.5, 1.9), (2.4, 1.0), (-2.6, -0.2), (2.7, -0.1)]
    for i, (cx, cy) in enumerate(kumeler):
        m = renkler[i % len(renkler)]
        for j in range(r.randint(3, 5)):
            boy = r.uniform(0.12, 0.26)
            k = kure("kristal", boy * 0.4, (cx + r.uniform(-0.25, 0.25), cy + r.uniform(-0.15, 0.15), boy * 0.8),
                     (0.45, 0.45, 2.2), m, kol, seg=6)
            k.rotation_euler = (r.uniform(-0.5, 0.5), r.uniform(-0.5, 0.5), 0)
        if i < 5:  # küme başına renkli, yumuşak ışık
            isik = bpy.data.lights.new(f"kristal_isik{i}", "POINT")
            isik.energy, isik.shadow_soft_size = 45, 0.4
            isik.color = m.diffuse_color[:3]
            ob = bpy.data.objects.new(f"kristal_isik{i}", isik)
            kol.objects.link(ob)
            ob.location = (cx, cy - 0.3, 0.5)
    for x, y in ((-1.9, 0.6), (1.9, 0.5), (-0.9, 1.6), (1.0, 1.5)):  # parlayan mantarlar
        silindir("mantar_sap", 0.04, 0.03, 0.14, (x, y, 0), malzeme("parlak_sap", (0.9, 0.95, 1.0), 0.6, isima=0.6), kol)
        kure("mantar_sapka", 0.12, (x, y, 0.15), (1, 1, 0.5), malzeme("parlak_mantar", (0.3, 0.95, 0.85), 0.4, isima=2.5),
             kol)


MEKAN_KUR = {}


def oda_kur(tohum, kol):
    zemin = malzeme("parke", (0.62, 0.42, 0.26), 0.6)
    duvar = malzeme("duvar", (0.98, 0.86, 0.74), 0.9)
    for ad, konum, olcek, m in (("zemin", (0, 1, -0.05), (6, 5, 0.05), zemin),
                                ("arka_duvar", (0, 4, 1.8), (6, 0.08, 1.9), duvar),
                                ("sol_duvar", (-5, 1, 1.8), (0.08, 5, 1.9), duvar),
                                ("sag_duvar", (5, 1, 1.8), (0.08, 5, 1.9), duvar)):
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2)
        ob = _nesne(ad, bm, m, kol, yumusak=False)
        ob.location, ob.scale = konum, olcek
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2)
    pen = _nesne("pencere", bm, malzeme("pencere", (0.65, 0.85, 1.0), 0.2, isima=1.5), kol, yumusak=False)
    pen.location, pen.scale = (1.6, 3.9, 2.0), (0.8, 0.05, 0.6)
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, segments=48, radius=1.6)
    hali = _nesne("hali", bm, malzeme("hali", (0.85, 0.35, 0.45), 0.95), kol, yumusak=False)
    hali.location, hali.scale = (0, 0.6, 0.003), (1.4, 0.9, 1)
    masa = malzeme("masa", (0.75, 0.52, 0.32), 0.6)
    silindir("masa_ayak", 0.07, 0.07, 0.55, (-2.4, 2.2, 0), masa, kol)
    silindir("masa_ust", 0.6, 0.6, 0.06, (-2.4, 2.2, 0.55), masa, kol, seg=32)
    kure("yatak", 0.7, (2.8, 2.6, 0.25), (1.4, 1, 0.4), malzeme("yatak", (0.55, 0.7, 0.95), 0.9), kol)
    isik = bpy.data.lights.new("lamba", "POINT")
    isik.energy, isik.color, isik.shadow_soft_size = 120, (1, 0.8, 0.55), 0.3
    ob = bpy.data.objects.new("lamba", isik)
    kol.objects.link(ob)
    ob.location = (-2.4, 2.2, 1.6)


def kis_kur(tohum, kol):
    """Karlı çam ormanı: kar zemin, karlı çamlar, kardan adam, uzakta karlı tepeler."""
    r = random.Random(tohum)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=60, y_segments=60, size=22)
    for v in bm.verts:
        d = math.hypot(v.co.x, v.co.y)
        v.co.z = 0.0 if d < 3 else 0.15 * math.sin(v.co.x * 0.6) * math.cos(v.co.y * 0.5) * min(1, (d - 3) / 3)
    _nesne("zemin", bm, malzeme("kar", (0.80, 0.84, 0.92), 0.85), kol)
    govde_m = malzeme("cam_govde", (0.34, 0.22, 0.13), 0.85)
    yesil = malzeme("cam_yaprak", (0.12, 0.36, 0.22), 0.8)
    kar = malzeme("kar_ust", (0.86, 0.89, 0.95), 0.7)

    def cam(x, y, o):
        silindir("cam", 0.12 * o, 0.1 * o, 0.6 * o, (x, y, 0), govde_m, kol, seg=10)
        for k in range(3):
            z = (0.5 + k * 0.55) * o
            rr = (0.9 - k * 0.25) * o
            silindir("cam_kat", rr, 0.02, 0.9 * o, (x, y, z), yesil, kol, seg=14)
            silindir("cam_kar", rr * 0.55, 0.02, 0.35 * o, (x, y, z + 0.45 * o), kar, kol, seg=14)

    cam(0.5, 3.4, 1.5)
    for i in range(20):
        a = r.uniform(-0.15, math.pi + 0.15)
        d = r.uniform(4.2, 11)
        cam(math.cos(a) * d * 1.3, math.sin(a) * d + 1.0, r.uniform(0.9, 1.5))
    for i in range(8):  # kar yığınları
        a = r.uniform(0, math.pi)
        d = r.uniform(2.6, 5)
        kure("kar_yigin", r.uniform(0.25, 0.5), (math.cos(a) * d * 1.2, math.sin(a) * d + 0.6, 0.0),
             (1.4, 1, 0.5), kar, kol, ico=True)
    # kardan adam (karakter alanının dışında, sağ arkada)
    beyaz = malzeme("kardan_adam", (0.88, 0.9, 0.95), 0.6)
    kure("ka_alt", 0.32, (2.3, 1.8, 0.28), (1, 1, 0.95), beyaz, kol)
    kure("ka_ust", 0.22, (2.3, 1.8, 0.75), (1, 1, 1), beyaz, kol)
    kure("ka_burun", 0.035, (2.3, 1.58, 0.76), (1, 3, 1), malzeme("havuc", (1.0, 0.45, 0.05), 0.5), kol)
    kure("ka_atki", 0.2, (2.3, 1.8, 0.56), (1.1, 1.1, 0.25), malzeme("atki", (0.85, 0.15, 0.2), 0.8), kol)
    for i in range(4):
        kure("tepe", 9, (-24 + i * 16, 30 + r.uniform(-3, 3), -5.5), (1.6, 1, 0.8),
             malzeme("karli_tepe", (0.88, 0.92, 0.98), 0.9), kol, ico=True)


def sahil_kur(tohum, kol):
    """Kumsal: kum zemin, arkada deniz, şemsiye, kumdan kale, deniz kabukları."""
    r = random.Random(tohum)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=40, y_segments=40, size=22)
    _nesne("zemin", bm, malzeme("kum", (0.86, 0.74, 0.5), 0.95), kol)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=4, y_segments=4, size=1)
    deniz = _nesne("deniz", bm, malzeme("deniz", (0.12, 0.5, 0.85), 0.1, isima=0.12), kol, yumusak=False)
    deniz.scale, deniz.location = (40, 14, 1), (0, 19, 0.03)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=4, y_segments=4, size=1)
    kopuk = _nesne("kopuk", bm, malzeme("kopuk", (0.97, 0.98, 1.0), 0.6), kol, yumusak=False)
    kopuk.scale, kopuk.location = (40, 0.25, 1), (0, 5.05, 0.035)
    # şemsiye (sol arka)
    silindir("semsiye_sap", 0.03, 0.03, 1.6, (-2.5, 2.2, 0), malzeme("semsiye_sap", (0.95, 0.95, 0.95)), kol)
    for i, renk in enumerate(((0.95, 0.25, 0.3), (1, 1, 1))):
        silindir(f"semsiye_{i}", 1.0 - i * 0.02, 0.02, 0.45, (-2.5, 2.2, 1.45 + i * 0.01),
                 malzeme(f"semsiye_{i}", renk, 0.6), kol, seg=8 if i == 0 else 16)
    # kumdan kale (sağ arka)
    kum_k = malzeme("kum_kale", (0.85, 0.72, 0.48), 0.95)
    silindir("kale", 0.35, 0.35, 0.3, (2.4, 2.0, 0), kum_k, kol, seg=16)
    for dx in (-0.25, 0.25):
        silindir("kule", 0.12, 0.1, 0.35, (2.4 + dx, 2.0, 0.3), kum_k, kol, seg=10)
    silindir("bayrak_sap", 0.01, 0.01, 0.3, (2.4, 2.0, 0.3), malzeme("bayrak_sap", (0.4, 0.3, 0.2)), kol)
    kure("bayrak", 0.06, (2.45, 2.0, 0.55), (1, 0.15, 0.6), malzeme("bayrak", (0.95, 0.2, 0.25)), kol)
    renkler = [malzeme(f"kabuk_{i}", c, 0.5) for i, c in enumerate(((1, 0.75, 0.75), (1, 0.9, 0.7), (0.95, 0.6, 0.4)))]
    for i in range(14):
        a = r.uniform(0, math.pi)
        d = r.uniform(2.2, 4.5)
        x, y = math.cos(a) * d * 1.2, math.sin(a) * d + 0.3
        kure("kabuk", 0.06, (x, y, 0.0), (1.3, 1, 0.4), r.choice(renkler), kol, seg=12)


def bahce_kur(tohum, kol):
    """Sebze bahçesi: çimen, tahta çit, havuç ve domates sıraları, ayçiçekleri."""
    r = random.Random(tohum)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=40, y_segments=40, size=22)
    _nesne("zemin", bm, malzeme("cimen", (0.30, 0.56, 0.20), 0.9), kol)
    toprak = malzeme("toprak", (0.42, 0.28, 0.16), 0.95)
    tahta = malzeme("cit", (0.78, 0.6, 0.4), 0.8)
    for x in [i * 0.6 - 6 for i in range(21)]:  # çit (arkada)
        silindir("cit_direk", 0.05, 0.05, 0.8, (x, 3.6, 0), tahta, kol, seg=6, yumusak=False)
    for z in (0.3, 0.6):
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2)
        ob = _nesne("cit_tahta", bm, tahta, kol, yumusak=False)
        ob.scale, ob.location = (6, 0.03, 0.05), (0, 3.6, z)
    yaprak = malzeme("sebze_yaprak", (0.2, 0.55, 0.18), 0.8)
    turuncu = malzeme("havuc", (1.0, 0.45, 0.05), 0.5)
    kirmizi = malzeme("domates", (0.9, 0.12, 0.1), 0.35)
    for sira, y in enumerate((1.6, 2.5)):
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=2)
        ob = _nesne("tarh", bm, toprak, kol, yumusak=False)
        ob.scale, ob.location = (3.4, 0.25, 0.04), (0, y, 0.0)
        for i in range(10):
            x = -3.0 + i * 0.66
            if sira == 0:
                kure("havuc_ust", 0.08, (x, y, 0.09), (1, 1, 0.5), turuncu, kol, seg=12)
                kure("havuc_yaprak", 0.1, (x, y, 0.2), (0.6, 0.6, 1.4), yaprak, kol, ico=True)
            else:
                kure("domates_dal", 0.22, (x, y, 0.25), (1, 1, 1.1), yaprak, kol, ico=True)
                for j in range(2):
                    kure("domates", 0.06, (x + r.uniform(-0.12, 0.12), y - 0.16, 0.2 + j * 0.12), (1, 1, 0.9),
                         kirmizi, kol, seg=12)
    sari = malzeme("aycicek", (1.0, 0.82, 0.1), 0.5)
    for x in (-3.2, 3.3):  # ayçiçekleri
        silindir("aycicek_sap", 0.03, 0.03, 1.4, (x, 3.2, 0), yaprak, kol, seg=8)
        kure("aycicek", 0.3, (x, 3.1, 1.45), (1, 0.3, 1), sari, kol)
        kure("aycicek_ic", 0.14, (x, 2.99, 1.45), (1, 0.3, 1), malzeme("aycicek_ic", (0.35, 0.2, 0.08), 0.8), kol)
    for i in range(4):
        kure("tepe", 9, (-24 + i * 16, 30 + r.uniform(-3, 3), -5.5), (1.6, 1, 0.8),
             malzeme("tepe", (0.36, 0.58, 0.42), 0.95), kol, ico=True)


MEKAN_KUR.update(orman=orman_kur, oda=oda_kur, dere=dere_kur, magara=magara_kur,
                 kis=kis_kur, sahil=sahil_kur, bahce=bahce_kur)


# ------------------------------------------------------------------ kurulum
def kur(plan_yolu, is_dizini, ornekleme=24, olcek=100):
    plan = json.loads(Path(plan_yolu).read_text())
    is_dizini = Path(is_dizini)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    # RENDER_MOTORU=CYCLES: ekran kartı olmayan bulut makinesinde işlemciyle render
    if os.environ.get("RENDER_MOTORU", "EEVEE").upper() == "CYCLES":
        sc.render.engine = "CYCLES"
        sc.cycles.device = "CPU"
        sc.cycles.samples = int(os.environ.get("CYCLES_ORNEK", max(4, int(ornekleme) // 2)))
        sc.cycles.use_denoising = True
        sc.cycles.max_bounces = 4
    else:
        sc.render.engine = "BLENDER_EEVEE"
    sc.eevee.taa_render_samples = int(ornekleme)
    for ozellik, deger in (("use_shadows", True), ("use_fast_gi", True), ("use_raytracing", False)):
        if hasattr(sc.eevee, ozellik):
            setattr(sc.eevee, ozellik, deger)
    sc.render.resolution_x, sc.render.resolution_y = plan["en"], plan["boy"]
    sc.render.resolution_percentage = int(olcek)
    sc.render.fps = plan["fps"]
    sc.frame_start, sc.frame_end = 0, plan["kare_say"] - 1
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    sc.render.use_overwrite = False
    sc.render.use_placeholder = True
    sc.render.filepath = str(is_dizini / "kareler" / "k_")
    # çizgi film renkleri doygun kalsın: AgX renkleri soldurur
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.exposure = -0.75

    dunya = bpy.data.worlds.new("dunya")
    sc.world = dunya
    dunya.use_nodes = True
    arka = dunya.node_tree.nodes["Background"]

    sahne_kol = bpy.data.collections.new("mekan")
    sc.collection.children.link(sahne_kol)
    tur = plan["mekan"]["tur"]
    MEKAN_KUR[tur](plan["mekan"].get("tohum", 1), sahne_kol)

    armlar, izler = {}, {}
    for k, t in plan["karakterler"].items():
        armlar[k], kol = karakter_kur(t)
        izler[k] = parmak_izi(kol)
    nesneler = {}
    for nid, t in plan["nesneler"].items():
        nesneler[nid] = NESNE_KUR[t.get("tur", "palamut")](nid, t["konum"], sahne_kol)
        for k in armlar:
            c = nesneler[nid].constraints.new("COPY_LOCATION")
            c.name = f"tut_{k}"
            c.target, c.subtarget, c.head_tail = armlar[k], "kol.R", 1.0
            c.influence = 0.0

    gunes_v = bpy.data.lights.new("gunes", "SUN")
    gunes_v.angle = math.radians(4)
    gunes = bpy.data.objects.new("gunes", gunes_v)
    sc.collection.objects.link(gunes)
    dolgu_v = bpy.data.lights.new("dolgu", "AREA")
    dolgu_v.size, dolgu_v.energy = 8, 140
    dolgu = bpy.data.objects.new("dolgu", dolgu_v)
    sc.collection.objects.link(dolgu)
    dolgu.location = (0, -7, 4)
    dolgu.rotation_euler = (math.radians(60), 0, 0)

    kam_v = bpy.data.cameras.new("kamera")
    kam_v.sensor_fit, kam_v.sensor_width = "AUTO", 36
    kam = bpy.data.objects.new("kamera", kam_v)
    sc.collection.objects.link(kam)
    sc.camera = kam
    hedef = bpy.data.objects.new("kamera_hedef", None)
    sc.collection.objects.link(hedef)
    iz = kam.constraints.new("TRACK_TO")
    iz.target, iz.track_axis, iz.up_axis = hedef, "TRACK_NEGATIVE_Z", "UP_Y"

    # --- anahtar kareler
    for f in range(plan["kare_say"]):
        for k, arm in armlar.items():
            p = plan["pozlar"][k][f]
            arm.location = p["konum"]
            arm.rotation_euler = (0, 0, p["yon"])
            arm.keyframe_insert("location", frame=f)
            arm.keyframe_insert("rotation_euler", frame=f)
            for b, rot in p["kemik"].items():
                pb = arm.pose.bones[b]
                pb.rotation_euler = rot
                pb.keyframe_insert("rotation_euler", frame=f)
            for b, olc in p["olcek"].items():
                pb = arm.pose.bones[b]
                pb.scale = olc
                pb.keyframe_insert("scale", frame=f)
        for nid, ob in nesneler.items():
            etkiler = plan["tutma"][nid][f]
            for k in armlar:
                c = ob.constraints[f"tut_{k}"]
                c.influence = etkiler.get(k, 0.0)
                c.keyframe_insert("influence", frame=f)
            kapak = bpy.data.objects.get(f"{nid}_kapak")
            if kapak:
                kapak.rotation_euler = (math.radians(-105) * etkiler.get("_ac", 0.0), 0, 0)
                kapak.keyframe_insert("rotation_euler", frame=f)
        kp = plan["kamera"][f]
        kam.location = kp["konum"]
        kam_v.lens = kp["lens"]
        hedef.location = kp["hedef"]
        kam.keyframe_insert("location", frame=f)
        kam_v.keyframe_insert("lens", frame=f)
        hedef.keyframe_insert("location", frame=f)
        ip = plan["isik"][f]
        gunes_v.energy, gunes_v.color = ip["gunes"], ip["renk"]
        gunes.rotation_euler = (math.radians(ip["egim"]), 0, math.radians(ip["yon"]))
        gunes_v.keyframe_insert("energy", frame=f)
        gunes_v.keyframe_insert("color", frame=f)
        gunes.keyframe_insert("rotation_euler", frame=f)
        arka.inputs[0].default_value = (*ip["gok"], 1)
        arka.inputs[1].default_value = ip["gok_guc"]
        arka.inputs[0].keyframe_insert("default_value", frame=f)
        arka.inputs[1].keyframe_insert("default_value", frame=f)

    (is_dizini / "kareler").mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(is_dizini / "sahne.blend"))

    # --- kare kare ölçüm (kalite kontrolü için)
    meta = {"parmak_izi": izler, "kareler": []}
    for f in range(plan["kare_say"]):
        sc.frame_set(f)
        kayit = {"kamera": [round(v, 4) for v in (*kam.matrix_world.translation,
                                                  *kam.matrix_world.to_euler())],
                 "gunes": round(gunes_v.energy, 3), "karakter": {}}
        for k, arm in armlar.items():
            pb = arm.pose.bones
            # baş = yüz ortası, gövde = gövde ortası (kemik uçları sıkı kadrajda dışarıda kalır)
            noktalar = {"bas": (pb["bas"].head + pb["bas"].tail) / 2,
                        "govde": (pb["govde"].head + pb["govde"].tail) / 2, "el.L": pb["kol.L"].tail,
                        "el.R": pb["kol.R"].tail, "ayak.L": pb["bacak.L"].tail, "ayak.R": pb["bacak.R"].tail}
            dunya_n = {n: arm.matrix_world @ v for n, v in noktalar.items()}
            gorunen = {}
            for n in dunya_n:  # baş, gövde, iki el, iki ayak
                c = world_to_camera_view(sc, kam, dunya_n[n])
                gorunen[n] = int(0 <= c.x <= 1 and 0 <= c.y <= 1 and c.z > 0)
            kayit["karakter"][k] = {
                "konum": [round(v, 4) for v in arm.matrix_world.translation],
                **{n: [round(x, 4) for x in v] for n, v in dunya_n.items()},
                "gorunur": sum(gorunen.values()) / len(dunya_n),
                "gorunen": gorunen,
                "agiz": round(pb["agiz"].scale.z, 4),
            }
        meta["kareler"].append(kayit)
    (is_dizini / "meta.json").write_text(json.dumps(meta))
    print("KURULUM_TAMAM", json.dumps(izler))


def render(is_dizini, bas, son):
    is_dizini = Path(is_dizini)
    bpy.ops.wm.open_mainfile(filepath=str(is_dizini / "sahne.blend"))
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = int(bas), int(son)
    bpy.ops.render.render(animation=True)
    print("RENDER_TAMAM", bas, son)


if __name__ == "__main__":
    arg = sys.argv[sys.argv.index("--") + 1:]
    if arg[0] == "kur":
        kur(*arg[1:])
    elif arg[0] == "render":
        render(*arg[1:])
    else:
        raise SystemExit(f"bilinmeyen komut {arg[0]}")
