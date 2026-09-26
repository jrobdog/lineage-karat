#!/usr/bin/env python3
"""Adapt the retained Fire OS policy to Lineage's standard audio policy engine."""
import xml.etree.ElementTree as ET


def convert(content: bytes) -> bytes:
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    root = ET.fromstring(content, parser=parser)
    if root.tag != 'audioPolicyConfiguration' or root.get('version') != '1.0':
        raise ValueError('Unexpected audio policy version')
    config = root.find('globalConfiguration')
    if config is None or config.get('engine_library') != 'custom_smp':
        raise ValueError('Require the original Amazon audio engine selection')
    primary = root.find('./modules/module[@name="primary"]')
    if primary is None:
        raise ValueError('Missing primary module')
    device = primary.find('./devicePorts/devicePort[@tagName="AVLS-Out"]')
    if device is None or device.get('type') != 'AUDIO_DEVICE_OUT_AVLS':
        raise ValueError('Unexpected AVLS device')
    # AVLS is Amazon's network/home-theater output, not the physical HDMI port.
    # Its unrecognized enum rejects the entire XML in the standard serializer.
    for parent_name, tag, attr, names in (
        ('mixPorts', 'mixPort', 'name', {'avls_out', 'avls_out_tunnel'}),
        ('devicePorts', 'devicePort', 'tagName', {'AVLS-Out'}),
        ('routes', 'route', 'sink', {'AVLS-Out'}),
    ):
        parent = primary.find(parent_name)
        matches = [node for node in parent if node.tag == tag and node.get(attr) in names]
        if len(matches) != len(names) or {node.get(attr) for node in matches} != names:
            raise ValueError('Unexpected AVLS branch layout')
        for node in matches:
            parent.remove(node)
    config.set('engine_library', 'default')
    for module in root.findall('./modules/module'):
        ports = ({node.get('name') for node in module.findall('./mixPorts/mixPort')} |
                 {node.get('tagName') for node in module.findall('./devicePorts/devicePort')})
        for route in module.findall('./routes/route'):
            if route.get('sink') not in ports or not all(
                source.strip() in ports for source in route.get('sources', '').split(',')
            ):
                raise ValueError('Unresolved route after AVLS removal')
        for node in module.findall('./attachedDevices/item') + [module.find('defaultOutputDevice')]:
            if node is not None and node.text not in ports:
                raise ValueError('Unresolved attached/default device')
    if primary.find('./devicePorts/devicePort[@tagName="HDMI-Out"]') is None:
        raise ValueError('HDMI output was lost')
    hdmi = primary.find('./routes/route[@sink="HDMI-Out"]')
    if hdmi is None or 'primary_out' not in hdmi.get('sources', '').split(','):
        raise ValueError('HDMI PCM route was lost')
    ET.register_namespace('xi', 'http://www.w3.org/2001/XInclude')
    ET.indent(root, space='    ')
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)
