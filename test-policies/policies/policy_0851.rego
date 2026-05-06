package governance.authentication.action.deny.policy_0851

# Auto-generated policy 851 (Rego v1 syntax)
# Package: governance.authentication.action.deny

# Metadata
metadata := {
    "policy_id": "0851",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0851_allowed if {
    input.user.role == "admin"
}
policy_0851_allowed if {
    data.policies.governance.enabled
}
policy_0851_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0851_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
