package security.monitoring.user.verify.policy_0401

# Auto-generated policy 401 (Rego v1 syntax)
# Package: security.monitoring.user.verify

# Metadata
metadata := {
    "policy_id": "0401",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0401_allowed = false
policy_0401_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
