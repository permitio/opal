package audit.validation.action.allow.policy_0014

# Auto-generated policy 14 (Rego v1 syntax)
# Package: audit.validation.action.allow

# Metadata
metadata := {
    "policy_id": "0014",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0014_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0014_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0014_allowed if {
    data.policies.audit.enabled
}
