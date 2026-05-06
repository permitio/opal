package compliance.authentication.context.deny.policy_0404

# Auto-generated policy 404 (Rego v1 syntax)
# Package: compliance.authentication.context.deny

# Metadata
metadata := {
    "policy_id": "0404",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0404_allowed = false
policy_0404_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0404_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
