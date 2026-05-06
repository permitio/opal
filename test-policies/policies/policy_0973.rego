package compliance.validation.user.allow.policy_0973

# Auto-generated policy 973 (Rego v1 syntax)
# Package: compliance.validation.user.allow

# Metadata
metadata := {
    "policy_id": "0973",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0973_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0973_allowed if {
    data.policies.compliance.enabled
}
policy_0973_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
