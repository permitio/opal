package audit.enforcement.context.verify.policy_0406

# Auto-generated policy 406 (Rego v1 syntax)
# Package: audit.enforcement.context.verify

# Metadata
metadata := {
    "policy_id": "0406",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0406_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0406_allowed = false
policy_0406_allowed if {
    data.policies.audit.enabled
}
policy_0406_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
