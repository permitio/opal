package audit.authentication.user.validate.policy_0005

# Auto-generated policy 5 (Rego v1 syntax)
# Package: audit.authentication.user.validate

# Metadata
metadata := {
    "policy_id": "0005",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0005_allowed if {
    input.user.role == "admin"
}
policy_0005_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0005_allowed if {
    data.policies.audit.enabled
}
policy_0005_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
