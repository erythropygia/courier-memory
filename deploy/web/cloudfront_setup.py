"""Web uygulamasına HTTPS adresi: ALB'nin önüne Amazon CloudFront (https://<id>.cloudfront.net).

Tarayıcı mikrofonu (getUserMedia: sesli not, Transcribe) ve ses tanıma yalnız HTTPS sayfada açılır; ALB adresi HTTP'dir.

  AWS_PROFILE=hackathon python deploy/web/cloudfront_setup.py

Dağıtım (tekrar çalıştırmak güvenlidir; yorum alanıyla bulunur):
  kaynak       ALB courier-memory-web, HTTP 80, yanıt bekleme 60 sn (ajan cevapları ve canlı akışlar)
  davranış     HTTP → HTTPS yönlendirme, bütün metodlar, önbellek kapalı (Managed-CachingDisabled),
               istek başlıkları/sorgu/çerez kaynağa gider (Managed-AllViewerExceptHostHeader)
"""
from __future__ import annotations

import sys
import time

COMMENT = "courier-memory-web"
ALB_NAME = "courier-memory-web"
CACHING_DISABLED = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"          # Managed-CachingDisabled
ALL_VIEWER_EXCEPT_HOST = "b689b0a8-53d0-40ab-baf2-68738e2966ac"    # Managed-AllViewerExceptHostHeader
ORIGIN_ID = "alb"


def distribution_config(alb_dns: str, caller_ref: str) -> dict:
    methods = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    return {
        "CallerReference": caller_ref, "Comment": COMMENT, "Enabled": True, "PriceClass": "PriceClass_100", "HttpVersion": "http2",
        "Origins": {"Quantity": 1, "Items": [{
            "Id": ORIGIN_ID, "DomainName": alb_dns,
            "CustomOriginConfig": {"HTTPPort": 80, "HTTPSPort": 443, "OriginProtocolPolicy": "http-only",
                                   "OriginReadTimeout": 60, "OriginKeepaliveTimeout": 60,
                                   "OriginSslProtocols": {"Quantity": 1, "Items": ["TLSv1.2"]}}}]},
        "DefaultCacheBehavior": {
            "TargetOriginId": ORIGIN_ID, "ViewerProtocolPolicy": "redirect-to-https", "Compress": True,
            "CachePolicyId": CACHING_DISABLED, "OriginRequestPolicyId": ALL_VIEWER_EXCEPT_HOST,
            "AllowedMethods": {"Quantity": len(methods), "Items": methods,
                               "CachedMethods": {"Quantity": 2, "Items": ["GET", "HEAD"]}}},
    }


def find_distribution(cf) -> dict | None:
    for page in cf.get_paginator("list_distributions").paginate():
        for d in (page.get("DistributionList") or {}).get("Items", []) or []:
            if d.get("Comment") == COMMENT:
                return d
    return None


def main(argv=None) -> int:
    import boto3

    s = boto3.Session()
    region = s.region_name or "us-east-1"
    alb = s.client("elbv2", region_name=region).describe_load_balancers(Names=[ALB_NAME])["LoadBalancers"][0]["DNSName"]
    cf = s.client("cloudfront")
    d = find_distribution(cf)
    if d is None:
        d = cf.create_distribution(DistributionConfig=distribution_config(alb, f"{COMMENT}-{int(time.time())}"))["Distribution"]
        print(f"  CloudFront dağıtımı oluşturuldu: {d['Id']} (yayılması 5-10 dk)")
    print(f"Hazır: https://{d['DomainName']}  (kaynak: http://{alb})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
