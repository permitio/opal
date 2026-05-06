package audit.enforcement.user.validate.policy_0366

# Auto-generated policy 366 (Rego v1 syntax)
# Package: audit.enforcement.user.validate

# Metadata
metadata := {
    "policy_id": "0366",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0366_allowed = false
policy_0366_allowed if {
    input.user.active
    input.resource.public
}
policy_0366_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
