import os
import json
import time
import subprocess
import uuid
import datetime
from typing import List, Dict, Any, Optional

from adt_core.standards.intent_matcher import match_intent_domain

class ClassificationResult:
    def __init__(
        self,
        run_id: str,
        engine: str,
        model: str,
        prompt_version: str,
        latency_ms: int,
        matched_domains: List[str],
        recommended_rrs: List[Dict[str, Any]],
        data_classifications: List[str],
        suggested_erasure_requirements: List[str],
        overall_confidence: float,
        raw_response: str,
        fallback_reason: Optional[str]
    ):
        self.run_id = run_id
        self.engine = engine
        self.model = model
        self.prompt_version = prompt_version
        self.latency_ms = latency_ms
        self.matched_domains = matched_domains
        self.recommended_rrs = recommended_rrs
        self.data_classifications = data_classifications
        self.suggested_erasure_requirements = suggested_erasure_requirements
        self.overall_confidence = overall_confidence
        self.raw_response = raw_response
        self.fallback_reason = fallback_reason

    def to_dict(self):
        return {
            "run_id": self.run_id,
            "engine": self.engine,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "latency_ms": self.latency_ms,
            "matched_domains": self.matched_domains,
            "recommended_rrs": self.recommended_rrs,
            "data_classifications": self.data_classifications,
            "suggested_erasure_requirements": self.suggested_erasure_requirements,
            "overall_confidence": self.overall_confidence,
            "raw_response": self.raw_response,
            "fallback_reason": self.fallback_reason
        }

def classify_intent(
    wish: str,
    users: str,
    success_v1: str,
    project_name: str,
    engine: str = "gemini-3.1-pro-high",
    prompt_version: str = "v1",
    timeout_s: int = 90,  # REQ-113: bumped from 20s — Flash-High needs breathing room with RR catalog in prompt
) -> ClassificationResult:
    run_id = f"cls_{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"
    start_time = time.time()
    
    framework_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    
    def fallback(reason: str, raw_response: str = "") -> ClassificationResult:
        latency_ms = int((time.time() - start_time) * 1000)
        matched_domains, baseline_rr_ids = match_intent_domain(wish)
        return ClassificationResult(
            run_id=run_id,
            engine="keyword_fallback",
            model=engine,
            prompt_version="spec072_v1",
            latency_ms=latency_ms,
            matched_domains=matched_domains,
            recommended_rrs=[{"id": rr, "rationale": "Recommended by intent matcher (fallback).", "confidence": 0.9} for rr in baseline_rr_ids],
            data_classifications=[],
            suggested_erasure_requirements=[],
            overall_confidence=0.0,
            raw_response=raw_response,
            fallback_reason=reason
        )

    try:
        prompt_path = os.path.join(framework_path, "_cortex", "prompts", "intent_classifier.md")
        if not os.path.exists(prompt_path):
            return fallback("Prompt template not found")
            
        with open(prompt_path, "r", encoding="utf-8") as f:
            prompt_template = f.read()

        intent_index_path = os.path.join(framework_path, "config", "intent_index.json")
        intent_index_json = "{}"
        if os.path.exists(intent_index_path):
            with open(intent_index_path, "r", encoding="utf-8") as f:
                intent_index_json = f.read()
                
        rr_catalog_json = "{}"
        try:
            from adt_core.standards.registry import StandardsRegistry
            reg = StandardsRegistry(os.path.join(framework_path, "_cortex", "standards"))
            all_rrs = []
            for std_meta in reg.get_index():
                std = reg.get_standard(std_meta["id"])
                if std:
                    for clause in std.clauses:
                        all_rrs.append({
                            "id": clause.id,
                            "title": getattr(clause, "title", clause.id),
                            "text": clause.text,
                            "derived_from": std_meta["id"],
                            "scope": getattr(clause, "scope", "")
                        })
            rr_catalog_json = json.dumps(all_rrs)
        except Exception as e:
            print("Failed to load RRs:", e)
            pass
            
        prompt = prompt_template.replace("{intent_index_json}", intent_index_json)
        prompt = prompt.replace("{rr_catalog_json}", rr_catalog_json)
        prompt = prompt.replace("{standards_summary}", "GDPR, ISO/IEC 42001, etc.")
        prompt = prompt.replace("{wish}", wish)
        prompt = prompt.replace("{users}", users)
        prompt = prompt.replace("{success_v1}", success_v1)
        
        import shutil
        agy_bin = os.environ.get("AGY_EXECPATH") or shutil.which("agy") or "agy"
        
        import tempfile
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".md") as tmp:
            tmp.write(prompt)
            tmp_name = tmp.name
            
        try:
            cmd = [agy_bin, "-p", tmp_name, "--dangerously-skip-permissions", "--model", engine]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
            
            raw_response = result.stdout
            
            json_str = raw_response
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0]
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0]
                
            try:
                parsed = json.loads(json_str.strip())
            except json.JSONDecodeError as je:
                return fallback(f"JSON Decode Error: {je}", raw_response)
                
            latency_ms = int((time.time() - start_time) * 1000)
            
            return ClassificationResult(
                run_id=run_id,
                engine=engine,
                model=engine,
                prompt_version=prompt_version,
                latency_ms=latency_ms,
                matched_domains=parsed.get("matched_domains", []),
                recommended_rrs=parsed.get("recommended_rrs", []),
                data_classifications=parsed.get("data_classifications", []),
                suggested_erasure_requirements=parsed.get("suggested_erasure_requirements", []),
                overall_confidence=parsed.get("overall_confidence", 0.0),
                raw_response=raw_response,
                fallback_reason=None
            )
            
        except subprocess.TimeoutExpired:
            return fallback(f"{engine} timeout after {timeout_s}s")
        except Exception as e:
            return fallback(str(e))
        finally:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)
                
    except Exception as e:
        return fallback(f"Outer exception: {e}")
