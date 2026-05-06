package audit.authentication.resource.verify.utils.policy_0204

# Auto-generated policy 204 (Rego v1 syntax)
# Package: audit.authentication.resource.verify.utils

# Metadata
metadata := {
    "policy_id": "0204",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0204_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0204_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0204_allowed if {
    data.policies.audit.enabled
}
policy_0204_allowed if {
    input.user.role == "admin"
}
