package compliance.enforcement.resource.check.policy_0380

# Auto-generated policy 380 (Rego v1 syntax)
# Package: compliance.enforcement.resource.check

# Metadata
metadata := {
    "policy_id": "0380",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0380_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0380_allowed = false
policy_0380_allowed if {
    input.user.role == "admin"
}
