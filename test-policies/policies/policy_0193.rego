package governance.enforcement.user.verify.helpers.policy_0193

# Auto-generated policy 193 (Rego v1 syntax)
# Package: governance.enforcement.user.verify.helpers

# Metadata
metadata := {
    "policy_id": "0193",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0193_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default policy_0193_allowed = false
policy_0193_allowed if {
    input.user.active
    input.resource.public
}
policy_0193_allowed if {
    input.user.role == "admin"
}
