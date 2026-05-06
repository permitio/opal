package compliance.authorization.action.check.policy_0865

# Auto-generated policy 865 (Rego v1 syntax)
# Package: compliance.authorization.action.check

# Metadata
metadata := {
    "policy_id": "0865",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0865_allowed if {
    input.user.role == "admin"
}
policy_0865_allowed if {
    data.policies.compliance.enabled
}
policy_0865_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0865_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
