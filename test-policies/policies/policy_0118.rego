package compliance.monitoring.user.verify.policy_0118

# Auto-generated policy 118 (Rego v1 syntax)
# Package: compliance.monitoring.user.verify

# Metadata
metadata := {
    "policy_id": "0118",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0118_allowed = false
policy_0118_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
