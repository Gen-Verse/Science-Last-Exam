"""ITK text rigid transforms, normalized to a physical matrix and offset.

ITK stores translation about a center, not the affine offset. Euler ordering
follows itkEuler3DTransform.hxx; fixed parameters include ComputeZYX.
"""
import math
from pathlib import Path
import re

IDENTITY = [1., 0., 0., 0., 1., 0., 0., 0., 1.]


def multiply(a, b):
    return [sum(a[3*i+k] * b[3*k+j] for k in range(3)) for i in range(3) for j in range(3)]


def apply(matrix, offset, point):
    return [sum(matrix[3*i+j] * point[j] for j in range(3)) + offset[i] for i in range(3)]


def inverse(matrix, offset):
    transposed = [matrix[3*j+i] for i in range(3) for j in range(3)]
    return transposed, apply(transposed, [0., 0., 0.], [-x for x in offset])


def rigid(matrix):
    transpose = [matrix[3*j+i] for i in range(3) for j in range(3)]
    error = max(abs(a-b) for a, b in zip(multiply(transpose, matrix), IDENTITY))
    a, b, c, d, e, f, g, h, i = matrix
    determinant = a*(e*i-f*h)-b*(d*i-f*g)+c*(d*h-e*g)
    return error < 1e-6 and abs(determinant - 1) < 1e-6


def _block(block):
    kind = block["Transform"].split('_')[0]
    parameters = [float(x) for x in block.get("Parameters", "").split()]
    fixed = [float(x) for x in block.get("FixedParameters", "").split()]
    if not all(math.isfinite(x) for x in parameters + fixed):
        raise ValueError("Nonfinite transform parameter")
    if kind == 'TranslationTransform' and len(parameters) == 3:
        matrix, translation, center = IDENTITY[:], parameters, [0., 0., 0.]
    elif kind in {'AffineTransform', 'MatrixOffsetTransformBase'} and len(parameters) == 12 and len(fixed) == 3:
        matrix, translation, center = parameters[:9], parameters[9:], fixed
    elif kind == 'Euler3DTransform' and len(parameters) == 6 and len(fixed) in {3, 4}:
        x, y, z = parameters[:3]
        cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
        rx = [1, 0, 0, 0, cx, -sx, 0, sx, cx]
        ry = [cy, 0, sy, 0, 1, 0, -sy, 0, cy]
        rz = [cz, -sz, 0, sz, cz, 0, 0, 0, 1]
        if len(fixed) == 4 and fixed[3] not in (0., 1.):
            raise ValueError("Invalid Euler ComputeZYX flag")
        matrix = multiply(multiply(rz, ry), rx) if len(fixed) == 4 and fixed[3] == 1 else multiply(multiply(rz, rx), ry)
        translation, center = parameters[3:], fixed[:3]
    elif kind == 'VersorRigid3DTransform' and len(parameters) == 6 and len(fixed) == 3:
        x, y, z = parameters[:3]
        norm = x*x+y*y+z*z
        if norm > 1 + 1e-12:
            raise ValueError("Invalid unit versor")
        w = math.sqrt(max(0., 1 - norm))
        matrix = [1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w),
                  2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w),
                  2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]
        translation, center = parameters[3:], fixed
    else:
        raise ValueError("Expected a supported 3-D rigid ITK transform")
    if not rigid(matrix):
        raise ValueError("Scale, shear and reflection are not rigid registration")
    offset = [translation[i] + center[i] - sum(matrix[3*i+j] * center[j] for j in range(3)) for i in range(3)]
    return matrix, offset


def transform_file(path):
    path = Path(path)
    if path.stat().st_size > 100000:
        raise ValueError("Transform file is too large")
    text = path.read_text(encoding='utf-8-sig')
    if not text.startswith('#Insight Transform File V1.0'):
        raise ValueError("Not an ITK transform file")
    blocks, current = [], None
    for line in text.splitlines():
        if line.startswith('Transform:'):
            if current is not None:
                blocks.append(current)
            current = {}
        if current is not None and ':' in line and not line.lstrip().startswith('#'):
            key, value = line.split(':', 1)
            if key.strip() in current:
                raise ValueError("Duplicate transform field")
            current[key.strip()] = value.strip()
    if current is not None:
        blocks.append(current)
    if blocks and blocks[0].get('Transform', '').startswith('CompositeTransform_'):
        blocks = blocks[1:]
    if not 1 <= len(blocks) <= 16:
        raise ValueError("Invalid number of transform blocks")
    matrix, offset = IDENTITY[:], [0., 0., 0.]
    # ITK CompositeTransform applies its queue in reverse order: T0(T1(...x)).
    for block in blocks:
        child_matrix, child_offset = _block(block)
        offset = apply(matrix, offset, child_offset)
        matrix = multiply(matrix, child_matrix)
    return matrix, offset
