package audit.enforcement.action.verify.policy_0042

# Auto-generated policy 42 (Rego v1 syntax)
# Package: audit.enforcement.action.verify

# Metadata
metadata := {
    "policy_id": "0042",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0042_allowed = false
policy_0042_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0042_allowed if {
    input.user.active
    input.resource.public
}
policy_0042_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
